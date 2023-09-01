import re
from flask import Flask, render_template, request, jsonify, session
import csv
import feedparser
from textblob import TextBlob
from datetime import datetime, timezone
from dateutil import parser
from dateutil import tz
import requests
import matplotlib.pyplot as plt


app = Flask(__name__)
app.secret_key = 'secret-key'


def fetch_news(feed_url):
    feed = feedparser.parse(feed_url)
    articles = []

    for entry in feed.entries:
        article = {
            'title': entry.title,
            'description': entry.summary,
            'link': entry.link,
            'published': entry.published,
            'sentiment': None
        }
        articles.append(article)

    return articles


def filter_articles_by_keyword_and_region(articles, keywords, region):

    filtered_articles = []
    all_keywords = ['energy'] + [keyword.strip() for keyword in keywords.split(',')]

    # Get the selected countries from the session
    selected_countries = session.get('selected_countries', [])

    # Split the region input into multiple regions (if provided)
    regions = [r.strip() for r in region.split(',')] if region else []

    for article in articles:
        contains_energy = any(keyword.lower() == 'energy' for keyword in all_keywords)
        contains_other_keywords = any(keyword.lower() in article['title'].lower() or keyword.lower() in article['description'].lower() for keyword in all_keywords if keyword.lower() != 'energy')
        contains_country = any(country.lower() in article['title'].lower() or country.lower() in article['description'].lower() for country in selected_countries)
        contains_region = any(region.lower() in article['title'].lower() or region.lower() in article['description'].lower() for region in regions)

        # Check if no region or keyword is specified
        if not region and not keywords and contains_energy:
            filtered_articles.append(article)
        elif not region and contains_other_keywords and contains_energy:
            filtered_articles.append(article)
        elif not keywords and (contains_country or contains_region) and contains_energy:
            filtered_articles.append(article)

        # Check if "Energy" and at least one other keyword are present,and at least one region/country is present
        elif contains_energy and contains_other_keywords and (contains_country or contains_region):
            filtered_articles.append(article)

    return filtered_articles


def perform_sentiment_analysis(articles):
    for article in articles:
        text = article['title'] + ' ' + article['description']
        blob = TextBlob(text)
        sentiment_score = blob.sentiment.polarity
        article['sentiment'] = sentiment_score


def categorize_articles(articles):
    positive_articles = []
    neutral_articles = []
    negative_articles = []

    for article in articles:
        if article['sentiment'] is not None:
            if article['sentiment'] > 0:
                positive_articles.append(article)
            elif article['sentiment'] == 0:
                neutral_articles.append(article)
            else:
                negative_articles.append(article)

    return positive_articles, neutral_articles, negative_articles


def read_feed_links_from_csv(file_path):
    feed_links = []

    with open(file_path, 'r', newline='') as csv_file:
        reader = csv.reader(csv_file)
        for row in reader:
            if len(row) > 0:
                feed_links.append(row[0])

    return feed_links


def filter_articles_by_date_range(articles, start_date_str, end_date_str):
    start_date = parser.parse(start_date_str).astimezone(tz.UTC)
    end_date = parser.parse(end_date_str).astimezone(tz.UTC) if end_date_str else datetime.now(tz.UTC)
   
    filtered_articles = [
        article for article in articles
        if start_date <= parser.parse(article['published']).astimezone(tz.UTC) <= end_date
    ]

    return filtered_articles


def generate_topic_pie_chart(articles):
    # Count the occurrences of each topic
    topics = {
        'solar': 0,
        'wind': 0,
        'oil and gas': 0,
        'natural gas': 0
    }

    for article in articles:
        text = article['title'] + ' ' + article['description']
        for topic in topics:
            if re.search(r'\b' + re.escape(topic) + r'\b', text.lower()):
                topics[topic] += 1

    # Remove topics with zero occurrences
    topics = {topic: count for topic, count in topics.items() if count > 0}

    # Prepare the data for the pie chart
    labels = topics.keys()
    values = topics.values()

    # Generate the pie chart
    plt.figure(figsize=(4, 4))
    plt.pie(values, labels=labels, autopct='%1.1f%%', startangle=90)

    # Add a title
    plt.title('Share of Topics in News Articles')

    # Adjust the border (square white space) around the pie chart
    # You can modify these values to control the white space around the pie chart
    plt.subplots_adjust(left=0.1, right=0.8, top=0.9, bottom=0.01)


    # Save the pie chart to a file
    # Adjust the dpi to change the resolution of the saved image (higher dpi means higher resolution)
    plt.savefig('static/topic_pie_chart.png', dpi=100)
    plt.close()


@app.route('/get_country', methods=['POST'])
def get_country(): 
    data = request.get_json()
    latitude = data['latitude']
    longitude = data['longitude']

    # Send a reverse geocoding request to Nominatim API to get the country
    url = f'https://nominatim.openstreetmap.org/reverse?format=json&lat={latitude}&lon={longitude}&accept-language=en'
    response = requests.get(url)

    if response.ok:
        data = response.json()
        country = data.get('address', {}).get('country')
       
        # Get the selected countries from the session
        selected_countries = session.get('selected_countries', [])
       
        # Add or remove the current country from the selected countries list
        if country and country not in selected_countries:
            selected_countries.append(country)
        elif country and country in selected_countries:
            selected_countries.remove(country)
       
        # Store the selected countries in the session variable
        session['selected_countries'] = selected_countries
       
        return jsonify({'country': country, 'selected_countries': selected_countries})
    else:
        return jsonify({'error': 'Failed to fetch country'}), 500


@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        keywords = request.form.get('keywords')
        start_date = request.form.get('start-date')
        end_date = request.form.get('end-date')

        # Read feed links from the CSV file
        feed_links = read_feed_links_from_csv('feed_links.csv')

        # Fetch news from the provided feed links
        all_articles = []
        for feed_link in feed_links:
            articles = fetch_news(feed_link)
            all_articles.extend(articles)

        # Filter articles based on keywords and date range
        filtered_articles = filter_articles_by_keyword_and_region(all_articles, keywords, request.form.get('region'))
        filtered_articles = filter_articles_by_date_range(filtered_articles, start_date, end_date)

        # Perform sentiment analysis on the filtered articles
        perform_sentiment_analysis(filtered_articles)

        # Categorize articles based on sentiment
        positive_articles, neutral_articles, negative_articles = categorize_articles(filtered_articles)

        # Generate the topic pie chart
        generate_topic_pie_chart(filtered_articles)

        current_date = datetime.now().strftime('%Y-%m-%d')
        return render_template('index.html',
                               positive_articles=positive_articles,
                               neutral_articles=neutral_articles,
                               negative_articles=negative_articles,
                               current_date=current_date)

    return render_template('index.html', current_date=datetime.now().strftime('%Y-%m-%d'))


if __name__ == '__main__':
    # Use the Agg backend for Matplotlib
    plt.switch_backend('agg')
    app.run(debug=True)