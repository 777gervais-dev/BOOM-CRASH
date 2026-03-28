import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime

st.set_page_config(layout="wide", page_title="Boom/Crash Trend Finder")

st.title("Application Trading — Identifier la Tendance Buy / Sell (Boom & Crash)")

st.markdown("Upload CSV with columns: timestamp, open, high, low, close. Timestamp in ISO or epoch. Or use sample data.")

# Upload
uploaded = st.file_uploader("Choisir un fichier CSV", type="csv")
if uploaded:
    df = pd.read_csv(uploaded)
else:
    st.info("Utilisation d'un jeu de données synthétique d'exemple.")
    periods = 500
    rng = pd.date_range(end=pd.Timestamp.now(), periods=periods, freq='T')
    np.random.seed(42)
    price = np.cumsum(np.random.randn(periods) * 0.5) + 1000
    high = price + np.random.rand(periods) * 0.8
    low = price - np.random.rand(periods) * 0.8
    openp = price + np.random.randn(periods) * 0.2
    close = price + np.random.randn(periods) * 0.2
    df = pd.DataFrame({"timestamp": rng, "open": openp, "high": high, "low": low, "close": close})

# Normalize timestamp
if not np.issubdtype(df['timestamp'].dtype, np.datetime64):
    try:
        df['timestamp'] = pd.to_datetime(df['timestamp'])
    except:
        try:
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s')
        except:
            st.error("Impossible de parser la colonne timestamp. Utiliser ISO ou epoch.")
            st.stop()

df = df.sort_values('timestamp').reset_index(drop=True)

# Indicators functions
def ema(series, length):
    return series.ewm(span=length, adjust=False).mean()

def rsi(series, length=14):
    delta = series.diff()
    up = delta.clip(lower=0)
    down = -1 * delta.clip(upper=0)
    ma_up = up.rolling(length).mean()
    ma_down = down.rolling(length).mean()
    rs = ma_up / (ma_down + 1e-9)
    return 100 - (100 / (1 + rs))

def macd(series, fast=12, slow=26, signal=9):
    ema_fast = ema(series, fast)
    ema_slow = ema(series, slow)
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    hist = macd_line - signal_line
    return macd_line, signal_line, hist

def atr(df, length=14):
    tr1 = df['high'] - df['low']
    tr2 = (df['high'] - df['close'].shift()).abs()
    tr3 = (df['low'] - df['close'].shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(length).mean()

def heikin_ashi(df):
    ha = pd.DataFrame(index=df.index)
    ha['close'] = (df['open'] + df['high'] + df['low'] + df['close']) / 4
    ha['open'] = (df['open'] + df['close']) / 2
    for i in range(1, len(df)):
        ha.at[df.index[i], 'open'] = (ha.at[df.index[i-1], 'open'] + ha.at[df.index[i-1], 'close']) / 2
    ha['high'] = df[['high', 'open', 'close']].join(ha[['open','close']]).max(axis=1)
    ha['low'] = df[['low', 'open', 'close']].join(ha[['open','close']]).min(axis=1)
    return ha

# Compute indicators
close = df['close']
df['ema10'] = ema(close, 10)
df['ema50'] = ema(close, 50)
df['rsi14'] = rsi(close, 14)
df['macd'], df['macd_signal'], df['macd_hist'] = macd(close)
df['atr14'] = atr(df, 14)
ha = heikin_ashi(df)
df[['ha_open','ha_high','haha_open','ha_high','ha_low','ha_close']] = ha[['open','high','low','close']]

# Signal logic
# Trend: ema10 > ema50 -> bullish, ema10 < ema50 -> bearish
df['trend'] = 0
df.loc[df['ema10'] > df['ema50'], 'trend'] = 1
df.loc[df['ema10'] < df['ema50'], 'trend'] = -1

# Confirmation: MACD histogram positive = momentum up, negative = momentum down
df['momentum'] = 0
df.loc[df['macd_hist'] > 0, 'momentum'] = 1
df.loc[df['macd_hist'] < 0, 'momentum'] = -1

# RSI filter: overbought/oversold
df['rsi_signal'] = 0
df.loc[df['rsi14'] < 30, 'rsi_signal'] = 1
df.loc[df['rsi14'] > 70, 'rsi_signal'] = -1

# Heikin-Ashi candle color (1 bullish, -1 bearish)
df['ha_color'] = 0
df.loc[df['ha_close'] > df['ha_open'], 'ha_color'] = 1
df.loc[df['ha_close'] < df['ha_open'], 'ha_color'] = -1

# Final Buy/Sell signals
# Buy when trend bullish, momentum bullish, HA bullish, and not RSI overbought
df['signal'] = ''
buy_cond = (df['trend'] == 1) & (df['momentum'] == 1) & (df['ha_color'] == 1) & (df['rsi_signal'] >= 0)
sell_cond = (df['trend'] == -1) & (df['momentum'] == -1) & (df['ha_color'] == -1) & (df['rsi_signal'] <= 0)
df.loc[buy_cond, 'signal'] = 'BUY'
df.loc[sell_cond, 'signal'] = 'SELL'

# Display controls
st.sidebar.subheader("Affichage")
show_ha = st.sidebar.checkbox("Montrer Heikin-Ashi", value=True)
show_ind = st.sidebar.checkbox("Montrer indicateurs", value=True)
latest_only = st.sidebar.checkbox("Montrer dernier signal seulement", value=True)

# Latest signal
latest = df.iloc[-1]
st.subheader(f"Dernier signal: {latest['signal'] or 'NEUTRE'}")
st.write(f"Timestamp: {latest['timestamp']}")
st.write(f"Prix close: {latest['close']:.5f}  |  EMA10: {latest['ema10']:.5f}  EMA50: {latest['ema50']:.5f}")
st.write(f"RSI14: {latest['rsi14']:.2f}  |  MACD_hist: {latest['macd_hist']:.6f}  |  ATR14: {latest['atr14']:.6f}")

# Chart
fig = go.Figure()

# Candles or HA
if show_ha:
    fig.add_trace(go.Candlestick(
        x=df['timestamp'],
        open=df['ha_open'],
        high=df['ha_high'],
        low=df['ha_low'],
        close=df['ha_close'],
        name='Heikin-Ashi',
        increasing_line_color='green', decreasing_line_color='red',
        opacity=0.9
    ))
else:
    fig.add_trace(go.Candlestick(
        x=df['timestamp'],
        open=df['open'],
        high=df['high'],
        low=df['low'],
        close=df['close'],
        name='Price',
        increasing_line_color='green', decreasing_line_color='red',
        opacity=0.9
    ))

# EMAs
fig.add_trace(go.Scatter(x=df['timestamp'], y=df['ema10'], mode='lines', name='EMA10', line=dict(width=1, color='blue')))
fig.add_trace(go.Scatter(x=df['timestamp'], y=df['ema50'], mode='lines', name='EMA50', line=dict(width=1, color='orange')))

# Signals markers
buys = df[df['signal'] == 'BUY']
sells = df[df['signal'] == 'SELL']
if not buys.empty:
    fig.add_trace(go.Scatter(x=buys['timestamp'], y=buys['close'], mode='markers', marker_symbol='triangle-up', marker_size=12, marker_color='lime', name='BUY'))
if not sells.empty:
    fig.add_trace(go.Scatter(x=sells['timestamp'], y=sells['close'], mode='markers', marker_symbol='triangle-down', marker_size=12, marker_color='magenta', name='SELL'))

fig.update_layout(xaxis_rangeslider_visible=False, height=600, margin=dict(l=10,r=10,t=40,b=10))
st.plotly_chart(fig, use_container_width=True)

# Indicators plots
if show_ind:
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("MACD")
        macd_fig = go.Figure()
        macd_fig.add_trace(go.Scatter(x=df['timestamp'], y=df['macd'], name='MACD', line=dict(color='black', width=1)))
        macd_fig.add_trace(go.Scatter(x=df['timestamp'], y=df['macd_signal'], name='Signal', line=dict(color='red', width=1)))
        macd_fig.add_trace(go.Bar(x=df['timestamp'], y=df['macd_hist'], name='Hist', marker_color='grey'))
        macd_fig.update_layout(height=250, margin=dict(l=10,r=10,t=10,b=10))
        st.plotly_chart(macd_fig, use_container_width=True)
    with col2:
        st.subheader("RSI & ATR")
        rsi_fig = go.Figure()
        rsi_fig.add_trace(go.Scatter(x=df['timestamp'], y=df['rsi14'], name='RSI14', line=dict(color='purple')))
        rsi_fig.add_hline(y=70, line_dash="dash", line_color="red")
        rsi_fig.add_hline(y=30, line_dash="dash", line_color="green")
        rsi_fig.update_layout(height=250, margin=dict(l=10,r=10,t=10,b=10))
        st.plotly_chart(rsi_fig, use_container_width=True)
        atr_fig = go.Figure()
        atr_fig.add_trace(go.Scatter(x=df['timestamp_df['timestamp'], y=df['atr14'], name='ATR14', line=dict(color='brown')))
        atr_fig.update_layout(height=200, margin=dict(l=10,r=10,t=10,b=10))
        st.plotly_chart(atr_fig, use_container_width=True)

# Signals table / history
st.subheader("Historique des signaux")
signals_df = df[df['signal'] != '']
if signals_df.empty:
    st.write("Aucun signal BUY/SELL détecté sur la période.")
else:
    display_df = signals_df[['timestamp','open','high','low','close','ema10','ema50','rsi14','macd_hist','atr14','signal']].copy()
    display_df['timestamp'] = display_df['timestamp'].astype(str)
    if latest_only:
        st.write(display_df.tail(1))
    else:
        st.write(display_df)

    # Download CSV
    csv = display_df.to_csv(index=False).encode('utf-8')
    st.download_button(label="Télécharger les signaux (CSV)", data=csv, file_name='signals.csv', mime='text/csv')

# Simple position sizing example (informative)
st.sidebar.subheader("Gestion de risque (exemple)")
acct = st.sidebar.number_input("Capital (ex)", min_value=1.0, value=1000.0, step=1.0)
risk_pct = st.sidebar.slider("Risque par trade (%)", min_value=0.1, max_value=10.0, value=1.0)
if not signals_df.empty:
    last_sig = signals_df.iloc[-1]
    # simple stop example: ATR-based
    if last_sig['signal'] == 'BUY':
        stop = last_sig['close'] - last_sig['atr14'] * 1.5
    else:
        stop = last_sig['close'] + last_sig['atr14'] * 1.5
    risk_amount = acct * (risk_pct / 100.0)
    qty = (risk_amount / abs(last_sig['close'] - stop)) if abs(last_sig['close'] - stop) > 0 else 0
    st.sidebar.write(f"Dernier signal: {last_sig['signal']} at {last_sig['close']:.5f}")
    st.sidebar.write(f"Stop suggéré: {stop:.5f}")
    st.sidebar.write(f"Taille position (ex): {qty:.3f}")

st.markdown("---")
st.markdown("Note: Ceci est un outil éducatif. Tester en démo avant tout usage réel. Pas de conseil financier.")

# End of app
