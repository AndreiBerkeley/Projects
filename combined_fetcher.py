import requests
import re
import pandas as pd
from datetime import datetime
import openpyxl
from openpyxl.utils.dataframe import dataframe_to_rows
from openpyxl.styles import Alignment
from openpyxl.worksheet.dimensions import DimensionHolder, ColumnDimension
from openpyxl.utils import get_column_letter
import time
from pathlib import Path
# Constants for DappRadar
DAPP_RADAR_API_KEY = ''
DAPP_RADAR_BASE_URL = 'https://apis.dappradar.com/v2/dapps/top/uaw'
DAPP_RADAR_RESULTS_TOP = 50
DAPP_RADAR_CATEGORY = 'games'
DAPP_RADAR_RANGE = '24h'
DAPP_RADAR_DAPP_URL = 'https://apis.dappradar.com/v2/dapps/'
# Constants for Artemis
ARTEMIS_API_KEY = ''
ARTEMIS_BASE_URL = 'https://api.artemisxyz.com'
GAME_NAMES = [
]
METRICS_OF_INTEREST = [
]
METRICS_MAPPING = {
}

file_path =  ''
# Function to fetch the top 50 ranking games based on UAW metric from DappRadar
def fetch_top_ranking_games():
    headers = {
        'accept': 'application/json',
        'x-api-key': DAPP_RADAR_API_KEY
    }
    params = {
        'category': DAPP_RADAR_CATEGORY,
        'range': DAPP_RADAR_RANGE,
        'top': DAPP_RADAR_RESULTS_TOP
    }
    try:
        response = requests.get(DAPP_RADAR_BASE_URL, headers=headers, params=params)
        response.raise_for_status()
        data = response.json()
        return data['results']
    except requests.exceptions.RequestException as e:
        print(f"Error fetching top ranking games from DappRadar: {e}")
        return []


# Function to clean HTML tags from text
def clean_html(raw_html):
    clean_re = re.compile('<.*?>|&([a-z0-9]+|#[0-9]{1,6}|#x[0-9a-f]{1,6});')
    cleantext = re.sub(clean_re, '', raw_html)
    return cleantext

def get_dapp_symbol(dapp_id):
    url = f"https://apis.dappradar.com/v2/dapps/{dapp_id}"
    headers = {
        "accept": "application/json",
        "x-api-key": DAPP_RADAR_API_KEY
    }

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        tokens = data['results'].get('tokens', [])
        if not tokens:
            print("No tokens found in the response.")
            return 'N/A'
        else:
            symbol = tokens[0].get('symbol', 'N/A')
            return symbol
    except requests.exceptions.RequestException as e:
        print(f"Error fetching Dapp symbol: {e}")
        return "N/A"

# Process the fetched data and map to desired structure
def process_dappradar_data(top_games):
    dapps = []
    for game in top_games:
        if 'games' in game.get('categories', []):
            dapp_id = game.get('dappId')
            metrics = game.get('metrics', {})
            description = game.get('fullDescription', 'N/A')
            cleaned_description = clean_html(description)
            symbol = get_dapp_symbol(dapp_id) if dapp_id else 'N/A'
            dapps.append({
                'Name': game.get('name', 'N/A'),
                'Symbol': symbol,
                'Website': game.get('website', 'N/A'),
                'Network': ', '.join(game.get('chains', [])),
                'Genre': ', '.join(game.get('categories', [])),
                'Unique Active Wallets (K) (30d)': metrics.get('uaw', 'N/A'),
                'Circulating Market Cap ($M)': metrics.get('balance', 'N/A'),
                'Volume ($M) (30d)': metrics.get('volume', 'N/A'),
                'Comments': cleaned_description
            })
    df = pd.DataFrame(dapps)
    return df
# Function to fetch supported assets from Artemis
def fetch_supported_assets():
    url = f"{ARTEMIS_BASE_URL}/asset"
    params = {"APIKey": ARTEMIS_API_KEY}
    response = requests.get(url, headers={"Accept": "application/json"}, params=params)
    return response.json().get('assets', [])

# Function to get valid Artemis IDs for the game names
def get_valid_artemis_ids(game_names, supported_assets):
    valid_ids = {}
    for game in game_names:
        for asset in supported_assets:
            if game.lower().replace(' ', '-') == asset['artemis_id']:
                valid_ids[game] = asset
                break
    return valid_ids

# Function to fetch available metrics for an Artemis ID
def fetch_available_metrics(artemis_id):
    url = f"{ARTEMIS_BASE_URL}/asset/{artemis_id}/metric"
    params = {"APIKey": ARTEMIS_API_KEY}
    response = requests.get(url, headers={"Accept": "application/json"}, params=params)
    if response.status_code == 200:
        return response.json().get('metrics', [])
    else:
        print(f"Error fetching metrics for {artemis_id}: {response.status_code}")
        return []

# Function to fetch data for a set of metrics for an Artemis ID
def fetch_metrics_data(artemis_id, metrics):
    metric_str = ','.join(metrics)
    url = f"{ARTEMIS_BASE_URL}/data/{metric_str}"
    params = {"artemisIds": artemis_id, "APIKey": ARTEMIS_API_KEY}
    response = requests.get(url, headers={"Accept": "application/json"}, params=params)
    if response.status_code == 200:
        return response.json().get('data', {}).get('artemis_ids', {}).get(artemis_id, {})
    else:
        print(f"Error fetching data for {artemis_id}: {response.status_code}")
        return {}

# Function to process the fetched Artemis data and map to desired structure
def process_artemis_data(valid_artemis_ids):
    data_list = []
    for game, asset in valid_artemis_ids.items():
        print(f"Processing {game}...")
        artemis_id = asset['artemis_id']
        symbol = asset['symbol']
        all_metrics = fetch_available_metrics(artemis_id)
        common_metrics = list(set(METRICS_OF_INTEREST).intersection(all_metrics))

        if common_metrics:
            data = fetch_metrics_data(artemis_id, common_metrics)
            game_data = {"Name": game, "Symbol": symbol}
            for metric in common_metrics:
                game_data[METRICS_MAPPING[metric]] = data.get(metric)
            data_list.append(game_data)
        else:
            print(f"No common metrics available for {game}")

    df = pd.DataFrame(data_list)
    return df

#Process Combined Artemis Data
def process_new_applications_data(file_path):
    df = pd.read_csv(file_path)
    print(df.columns)  # Print the headers to verify
    df = df.sort_values(by='activeAddresses', ascending=False)
    return df

def process_affinity_file(file_path):
    # Load the excel file and print the column names to verify
    df = pd.read_excel(file_path)
    print("Affinity file columns:", df.columns)
    return df


def process_combined_cryptorank_data():
    file_path = Path(__file__).with_name('')
    df = pd.read_excel(file_path, sheet_name='')
    print("Processed CryptoRank Columns:", df.columns)
    return df

def process_vesting_file(file_path):
    df = pd.read_csv(file_path, header=None, encoding='ISO-8859-1', usecols=[0, 1, 2, 3, 4, 5, 6, 8])
    df.columns = ['Company Name', 'Percentage Unlocked', 'Percentage Locked', 'Unlocked Value', 'Locked Value', 'Next Round Value (%)', 'Next Round Value ($)', 'Date of Next Unlock']
    # Extract the first string in 'Unlocked Value' to create 'Token Ticker' column
    df['Token Ticker'] = df['Unlocked Value'].apply(lambda x: str(x).split()[0] if pd.notna(x) else 'N/A')
    # Reorder columns to insert 'Token Ticker' after 'Company Name'
    columns = ['Company Name', 'Token Ticker', 'Percentage Unlocked', 'Percentage Locked', 'Unlocked Value', 'Locked Value', 'Next Round Value (%)', 'Next Round Value ($)', 'Date of Next Unlock']
    df = df[columns]
    return df
def get_all_coingecko_ids():
    url = "https://api.coingecko.com/api/v3/coins/list"
    headers = {
        "accept": "application/json",
        "x-cg-demo-api-key": ""
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return {coin['name']: coin['id'] for coin in response.json()}

# Function to add CoinGecko hyperlinks and exchanges data

def add_coingecko_hyperlink(df, name_column):
    coingecko_ids = get_all_coingecko_ids()
    def fetch_exchanges(coin_id):
        url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/tickers"
        headers = {
            "accept": "application/json",
            "x-cg-demo-api-key": ""
        }
        try:
            response = requests.get(url, headers=headers)
            if response.status_code == 200:
                tickers = response.json().get('tickers', [])
                exchanges = [ticker['market']['name'] for ticker in tickers]
                return exchanges[:10] + ["N/A"] * (10 - len(exchanges))  # Ensure list has exactly 10 items
            else:
                return ["N/A"] * 10
        except Exception as e:
            return ["N/A"] * 10

    def check_coingecko_link(name):
        coin_id = coingecko_ids.get(name)
        if coin_id:
            return coin_id
        return None

    if name_column not in df.columns:
        print(f"Column {name_column} not found in DataFrame. Available columns: {df.columns}")
        return df

    df = df.copy()
    df['CoinGecko ID'] = df[name_column].apply(lambda x: check_coingecko_link(x))

    valid_rows = df.dropna(subset=['CoinGecko ID']).head(30)
    valid_indices = valid_rows.index

    df['CoinGecko Link'] = df[name_column].apply(lambda x: f'=HYPERLINK("https://www.coingecko.com/en/coins/{x.lower().replace(" ", "-")}", "{x}")')

    exchanges_list = []
    for coin_id in valid_rows['CoinGecko ID']:
        exchanges = fetch_exchanges(coin_id)
        exchanges_list.append(exchanges)
        time.sleep(2)  # Respect the rate limit (30 requests per minute)

    exchanges_df = pd.DataFrame(exchanges_list, columns=[f'Exchange_{i+1}' for i in range(10)], index=valid_indices)
    for i in range(10):
        df[f'Exchange_{i+1}'] = "N/A"

    df.update(exchanges_df)
    return df

def fetch_top_gaming_cryptos():
    url = "https://api.coingecko.com/api/v3/coins/markets"
    params = {
        'vs_currency': 'usd',
        'category': 'gaming',
        'order': 'market_cap_desc',
        'per_page': 90,
        'page': 1
    }
    response = requests.get(url, params=params)
    response.raise_for_status()
    return response.json()

# Fetch the exchange platforms for a given cryptocurrency from CoinGecko
def fetch_crypto_exchanges(coin_id):
    url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/tickers"
    headers = {
        "accept": "application/json",
        "x-cg-demo-api-key": ""
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        tickers = response.json().get('tickers', [])
        exchanges = [ticker['market']['name'] for ticker in tickers]
        return exchanges[:10]  # Return top 10 exchanges
    else:
        return ["N/A"] * 10

# Process the top gaming cryptocurrencies and return as a DataFrame
def process_top_gaming_cryptos():
    top_gaming_cryptos = fetch_top_gaming_cryptos()
    crypto_data = []
    for crypto in top_gaming_cryptos:
        coin_id = crypto['id']
        name = crypto['name']
        symbol = crypto['symbol']
        exchanges = fetch_crypto_exchanges(coin_id)
        crypto_data.append({
            'Name': name,
            'Ticker Symbol': symbol,
            'Exchanges': ', '.join(exchanges)
        })
    df = pd.DataFrame(crypto_data)
    return df

#Combined_Excel
def create_combined_excel(top_gaming_cryptos_df, dappradar_df, artemis_df, cryptorank_df, new_applications_df, vesting_df,  common_affinity_cryptorank, common_artemis_cryptorank, common_dappradar_cryptorank, common_applications_cryptorank, affinity_df, file_path):
    # Function to detect and remove URL columns
    def remove_url_columns(df):
        url_columns = df.apply(lambda col: col.astype(str).str.startswith('http').any())
        return df.loc[:, ~url_columns]

    artemis_df = remove_url_columns(artemis_df)
    new_applications_df = remove_url_columns(new_applications_df)
    cryptorank_df = remove_url_columns(cryptorank_df)
    # Sort cryptorank_df by 'Market Cap'
    cryptorank_df = cryptorank_df.sort_values(by='Market Cap', ascending=False)
    with pd.ExcelWriter(file_path, engine='xlsxwriter') as writer:
        # Helper function to set column widths based on max length of data and column name
        def set_column_widths(worksheet, df):
            for idx, col in enumerate(df.columns):
                max_len = max(df[col].dropna().astype(str).map(len).max(), len(col)) + 2 if not df[col].empty else len(col) + 2
                worksheet.set_column(idx, idx, max_len)


        # Sheet 1: DappRadar
        dappradar_df.to_excel(writer, index=False, sheet_name='DappRadar')
        dappradar_worksheet = writer.sheets['DappRadar']
        set_column_widths(dappradar_worksheet, dappradar_df)

        # Sheet 2: Artemis
        artemis_df.to_excel(writer, index=False, sheet_name='Artemis')
        artemis_worksheet = writer.sheets['Artemis']
        set_column_widths(artemis_worksheet, artemis_df)

        # Sheet 3: CryptoRank
        if 'Date of Next Unlock' in cryptorank_df.columns:
            cryptorank_df['Date of Next Unlock'] = pd.to_datetime(cryptorank_df['Date of Next Unlock'], errors='coerce')
            cryptorank_df = cryptorank_df.sort_values(by='Date of Next Unlock', ascending=True)
        cryptorank_df.to_excel(writer, index=False, sheet_name='CryptoRank')
        cryptorank_worksheet = writer.sheets['CryptoRank']
        set_column_widths(cryptorank_worksheet, cryptorank_df)


        # Extra Sourcing
        new_applications_df.to_excel(writer, index=False, sheet_name='Extra_Sourcing')
        extra_sourcing_worksheet = writer.sheets['Extra_Sourcing']
        set_column_widths(extra_sourcing_worksheet, new_applications_df)

        # Vesting Information
        vesting_df_sorted = vesting_df.sort_values(by='Date of Next Unlock', ascending=True)
        vesting_df_sorted.to_excel(writer, index=False, sheet_name='vesting_cryptorank')
        vesting_cryptorank_worksheet = writer.sheets['vesting_cryptorank']
        set_column_widths(vesting_cryptorank_worksheet, vesting_df_sorted)


        # Add the CoinGecko gaming cryptocurrencies sheet
        top_gaming_cryptos_df.to_excel(writer, index=False, sheet_name='Top_CoinGecko_Gaming')
        top_gaming_cryptos_worksheet = writer.sheets['Top_CoinGecko_Gaming']
        set_column_widths(top_gaming_cryptos_worksheet, top_gaming_cryptos_df)

        # Add a separate sheet for Affinity data
        affinity_df.to_excel(writer, index=False, sheet_name='Affinity_Data')
        affinity_worksheet = writer.sheets['Affinity_Data']
        set_column_widths(affinity_worksheet, affinity_df)

    print(f"Excel file has been created at: {file_path}")

from pathlib import Path

def main():
    # Define the file paths using Path
    dappradar_file = Path(__file__).with_name('')
    affinity_file = Path(__file__).with_name('')
    vesting_file_1 = Path(__file__).with_name('')
    vesting_file_2 = Path(__file__).with_name('')
    applications_file = Path(__file__).with_name('')

    # Fetch data from DappRadar
    top_games = fetch_top_ranking_games()
    if not top_games:
        print("No top ranking games fetched from DappRadar.")
    dappradar_df = process_dappradar_data(top_games)

    # Process the affinity file
    affinity_df = process_affinity_file(affinity_file)

    # Fetch supported assets and process data from Artemis
    supported_assets = fetch_supported_assets()
    valid_artemis_ids = get_valid_artemis_ids(GAME_NAMES, supported_assets)
    artemis_df = process_artemis_data(valid_artemis_ids)

    # Process the vesting files
    vesting_df1 = process_vesting_file(vesting_file_1)
    vesting_df2 = process_vesting_file(vesting_file_2)
    vesting_df = pd.concat([vesting_df1, vesting_df2])

    # Process the combined cryptorank data
    cryptorank_df = process_combined_cryptorank_data()

    # Process new applications data
    new_applications_df = process_new_applications_data(applications_file)

    # Find common companies
    common_artemis_cryptorank = set(artemis_df['Name']).intersection(set(cryptorank_df['Company Name']))
    common_dappradar_cryptorank = set(dappradar_df['Name']).intersection(set(cryptorank_df['Company Name']))
    common_applications_cryptorank = set(new_applications_df['label']).intersection(set(cryptorank_df['Company Name']))
    common_affinity_cryptorank = set(affinity_df['Organization Name']).intersection(set(cryptorank_df['Company Name']))
    top_gaming_cryptos_df = process_top_gaming_cryptos()
    # Create a combined Excel file with the updated structure
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_path = Path(__file__).with_name(f'top_blockchain_gaming_{timestamp}.xlsx')
    create_combined_excel(top_gaming_cryptos_df, dappradar_df, artemis_df, cryptorank_df, new_applications_df, vesting_df, common_affinity_cryptorank, common_artemis_cryptorank, common_dappradar_cryptorank, common_applications_cryptorank, affinity_df, file_path)

if __name__ == "__main__":
    main()
