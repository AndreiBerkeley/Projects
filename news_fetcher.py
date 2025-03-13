import newspaper
from newspaper import news_pool
import spacy
import pandas as pd
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
import os
import logging
with open("combined_fetcher.py") as file:
    exec(file.read())
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Load SpaCy model
nlp = spacy.load('en_core_web_sm')

# Define the list of news sources
news_sources = [
]

# Build newspaper objects for each source
papers = [newspaper.build(source, memoize_articles=False) for source in news_sources]

# Set the news pool with threads
news_pool.set(papers, threads_per_source=2)
news_pool.join()

# Function to summarize text using SpaCy
def summarize_text(text):
    doc = nlp(text)
    sentences = [sent.text for sent in doc.sents]
    summary_length = min(5, len(sentences))  # Get up to 5 sentences for the summary
    summary = ' '.join(sentences[:summary_length])
    return summary

# Function to clean up and filter articles
def filter_articles(articles):
    filtered_articles = []
    seen_titles = set()
    unwanted_phrases = [
    ]

    for article in articles:
        if any(phrase in article['title'] for phrase in unwanted_phrases):
            continue
        if article['title'] in seen_titles:
            continue
        seen_titles.add(article['title'])
        filtered_articles.append(article)

    return filtered_articles

# Fetch and summarize articles
def fetch_and_summarize_articles(papers):
    articles_info = []

    for paper in papers:
        logging.info(f"Processing paper: {paper.brand}")
        if not paper.articles:
            logging.info(f"No articles found for {paper.brand}")
            continue
        for article in paper.articles[:7]:  # Get the first 7 articles from each source
            try:
                article.download()
                article.parse()
                article.nlp()
                summary = summarize_text(article.text)

                articles_info.append({
                    'title': article.title,
                    'summary': summary,
                    'url': article.url,
                    'html': article.article_html
                })
            except Exception as e:
                logging.error(f"Error parsing article from {article.url}: {e}")

    return filter_articles(articles_info)

articles_info = fetch_and_summarize_articles(papers)

# Write articles to a text file
def write_articles_to_txt(articles_info, file_path):
    with open(file_path, 'w', encoding='utf-8') as f:
        for article in articles_info:
            f.write(f"**__{article['title']}__**\n")
            f.write(f"{article['summary']}\n")
            f.write(f"URL: {article['url']}\n\n")

txt_file_path = ""
write_articles_to_txt(articles_info, txt_file_path)

# Email configuration
my_email = ''
password_key = ''
recipient_email = ''
subject = 'Crypto News Summaries'
smtp_server = "smtp.gmail.com"
smtp_port = 587

# Read the text file content
with open(txt_file_path, 'r', encoding='utf-8') as f:
    text_content = f.read()

# Create the email content with the articles
html_content = text_content.replace("**__", "<b><u>").replace("__**", "</u></b>").replace("\n", "<br>")

# Create email message
message = MIMEMultipart()
message['From'] = my_email
message['To'] = recipient_email
message['Subject'] = subject
message.attach(MIMEText(html_content, 'html'))

# Attach the Excel file
excel_file_path = ''
with open(excel_file_path, 'rb') as f:
    file_attachment = MIMEApplication(f.read(), name=os.path.basename(excel_file_path))
    file_attachment['Content-Disposition'] = f'attachment; filename="{os.path.basename(excel_file_path)}"'
    message.attach(file_attachment)

# Send email
with smtplib.SMTP(smtp_server, smtp_port) as server:
    server.starttls()
    server.login(my_email, password_key)
    server.sendmail(my_email, recipient_email, message.as_string())

print("Email sent successfully.")
