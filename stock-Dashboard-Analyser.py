# Step 1: Install dependencies

# Step 2: Import libraries
from flask import Flask, render_template_string, request
from pyngrok import ngrok
import yfinance as yf
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from statsmodels.tsa.arima.model import ARIMA
from textblob import TextBlob
import io
import os
import base64
from threading import Thread

# Step 3: Define Flask app
app = Flask(__name__)

# Step 4: HTML Templates
index_html = '''
<!DOCTYPE html>
<html>
<head><title>Stock Dashboard</title></head>
<body>
<h2>📈 Stock Market Dashboard</h2>
<form method="POST" action="/result">
    <label>Stock Symbol:</label>
    <input type="text" name="ticker" value="AAPL" required><br><br>

    <label>Moving Average Period:</label>
    <input type="number" name="ma_period" value="20"><br><br>

    <label>Bollinger Band Period:</label>
    <input type="number" name="bb_period" value="20"><br><br>

    <label>Compare Stocks:</label><br>
    {% for stock in stock_list %}
        <input type="checkbox" name="compare_stocks" value="{{ stock }}" {% if stock in ['AAPL','MSFT'] %}checked{% endif %}> {{ stock }}<br>
    {% endfor %}
    <br><input type="submit" value="Analyze">
</form>
</body></html>
'''

result_html = '''
<!DOCTYPE html>
<html><head><title>{{ ticker }} Results</title></head>
<body>
<h2>📊 Results for {{ ticker }}</h2>

<h3>📌 Moving Average</h3>
<img src="data:image/png;base64,{{ ma_img }}"><br>

<h3>📌 Bollinger Bands</h3>
<img src="data:image/png;base64,{{ bb_img }}"><br>

<h3>📌 ARIMA Forecast</h3>
{% if arima_img %}
<img src="data:image/png;base64,{{ arima_img }}"><br>
{% else %}
<p>Forecasting Failed.</p>
{% endif %}


{% if corr_img %}
<h3>📌 Market Correlation</h3>
<img src="data:image/png;base64,{{ corr_img }}"><br>
{% endif %}

<br><a href="/">⬅ Go Back</a>
</body></html>
'''

# Step 5: Utility - Convert matplotlib plot to base64 image
def plot_to_img(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches='tight')
    buf.seek(0)
    encoded = base64.b64encode(buf.read()).decode('utf-8')
    buf.close()
    return encoded

# Step 6: Flask Routes
@app.route("/", methods=["GET"])
def index():
    stock_list = ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA"]
    return render_template_string(index_html, stock_list=stock_list)

@app.route("/result", methods=["POST"])
def result():
    ticker = request.form.get("ticker").upper()
    ma = int(request.form.get("ma_period"))
    bb = int(request.form.get("bb_period"))
    compare_stocks = request.form.getlist("compare_stocks")

    stock = yf.Ticker(ticker)
    stock_data = stock.history(period="1y")
    if stock_data.empty:
        return f"<h3>Invalid stock symbol {ticker}</h3>"

    # Moving Average Plot
    stock_data["MA"] = stock_data["Close"].rolling(ma).mean()
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(stock_data.index, stock_data["Close"], label="Close Price")
    ax.plot(stock_data.index, stock_data["MA"], label=f"{ma}-Day MA", linestyle="dashed")
    ax.legend()
    ax.set_title(f"{ticker} - Moving Average")
    ma_img = plot_to_img(fig)
    plt.close(fig)

    # Bollinger Bands Plot
    stock_data["Middle"] = stock_data["Close"].rolling(bb).mean()
    std = stock_data["Close"].rolling(bb).std()
    stock_data["Upper"] = stock_data["Middle"] + (2 * std)
    stock_data["Lower"] = stock_data["Middle"] - (2 * std)
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(stock_data.index, stock_data["Close"], label="Close Price")
    ax.plot(stock_data.index, stock_data["Upper"], label="Upper Band", linestyle="dashed")
    ax.plot(stock_data.index, stock_data["Lower"], label="Lower Band", linestyle="dashed")
    ax.fill_between(stock_data.index, stock_data["Lower"], stock_data["Upper"], color="gray", alpha=0.2)
    ax.legend()
    ax.set_title(f"{ticker} - Bollinger Bands")
    bb_img = plot_to_img(fig)
    plt.close(fig)

    # ARIMA Forecast Plot
    try:
        train_size = int(len(stock_data) * 0.8)
        train, test = stock_data["Close"][:train_size], stock_data["Close"][train_size:]
        model = ARIMA(train, order=(5, 1, 0))
        model_fit = model.fit()
        forecast = model_fit.forecast(steps=len(test))
        fig, ax = plt.subplots(figsize=(10, 4))
        ax.plot(train.index, train, label="Train")
        ax.plot(test.index, test, label="Test")
        ax.plot(test.index, forecast, label="Forecast", linestyle="dashed")
        ax.legend()
        ax.set_title(f"{ticker} - ARIMA Forecast")
        arima_img = plot_to_img(fig)
        plt.close(fig)
    except Exception as e:
        print(f"ARIMA Error: {e}")
        arima_img = None

    # News Sentiment Analysis
    news = []
    try:
        news_data = stock.news
        for article in news_data[:5]:
            title = article.get("title", "No Title")
            sentiment = TextBlob(title).sentiment.polarity
            sentiment_text = "Positive" if sentiment > 0 else "Negative" if sentiment < 0 else "Neutral"
            news.append({"title": title, "sentiment": sentiment_text, "score": round(sentiment, 2)})
    except Exception as e:
        print(f"News Fetch Error: {e}")
        news = None

    # Correlation Heatmap
    corr_img = None
    if len(compare_stocks) > 1:
        df = pd.DataFrame()
        for s in compare_stocks:
            prices = yf.Ticker(s).history(period="1y")["Close"]
            if not prices.empty:
                df[s] = prices
        if not df.empty:
            fig, ax = plt.subplots(figsize=(8, 5))
            sns.heatmap(df.corr(), annot=True, cmap="coolwarm", ax=ax)
            ax.set_title("Market Correlation")
            corr_img = plot_to_img(fig)
            plt.close(fig)

    return render_template_string(result_html, ticker=ticker, ma_img=ma_img, bb_img=bb_img,
                                  arima_img=arima_img, news=news, corr_img=corr_img)

# Step 7: Start Flask + ngrok
os.system("kill -9 $(lsof -t -i:5000)")
os.system("pkill ngrok")
import time
time.sleep(2)

def run_app():
    app.run(port=5000)

def start_ngrok():
    NGROK_AUTH_TOKEN = "2uX6QgqI0GgB3iQNH8c5rhD3TOO_2fbsnUiojnofhfXf5G7iX"  # Replace with your ngrok authtoken
    ngrok.set_auth_token(NGROK_AUTH_TOKEN)
    public_url = ngrok.connect(5000)
    print(f"🚀 Your Flask app is live here: {public_url}")

# Step 8: Launch
Thread(target=run_app).start()
start_ngrok()
