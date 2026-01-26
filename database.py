import sqlite3
from datetime import datetime, timezone
import pandas as pd
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

Base = declarative_base()

class PortfolioSettings(Base):
    __tablename__ = 'portfolio_settings'
    id = Column(Integer, primary_key=True)
    key = Column(String(50), unique=True)
    value = Column(Float)

class TradingLog(Base):
    __tablename__ = 'trading_log'
    
    id = Column(Integer, primary_key=True)
    data_operazione = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    strumento = Column(String(50), nullable=False)
    isin = Column(String(20)) # ISIN Code
    tipologia = Column(String(50))  # ETF, Azioni, Forex, Materie Prime, Crypto
    categoria = Column(String(50))  # Azioni, Obbligazioni, Certificati, Altri
    valuta = Column(String(10), default='EUR')
    stato = Column(String(20), default='APERTA')  # APERTA / CHIUSA
    quantità = Column(Float, nullable=False)
    prezzo_entrata = Column(Float, nullable=False)
    prezzo_medio_carico = Column(Float)
    prezzo_uscita = Column(Float)
    prezzo_attuale = Column(Float)
    costi_apertura = Column(Float, default=0.0)
    costi_chiusura = Column(Float, default=0.0)
    costo_mantenimento_annuo = Column(Float, default=0.20) # In percentage
    investito_lordo = Column(Float)
    investito_netto = Column(Float)
    valore_attuale = Column(Float)
    plus_minus = Column(Float)
    tassazione = Column(Float)  # 26% sulle plusvalenze
    net_profit = Column(Float)
    rendimento_percentuale = Column(Float)
    note = Column(Text)

# Database Setup
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if DATABASE_URL:
    # Neon/Heroku often use 'postgres://' but SQLAlchemy 1.4+ requires 'postgresql://'
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    engine = create_engine(DATABASE_URL)
else:
    DB_NAME = 'trading_journal.db'
    engine = create_engine(f'sqlite:///{DB_NAME}')

Session = sessionmaker(bind=engine)

def init_db():
    Base.metadata.create_all(engine)
    # Initialize initial balance if not exists
    session = Session()
    try:
        if not session.query(PortfolioSettings).filter_by(key='saldo_iniziale').first():
            session.add(PortfolioSettings(key='saldo_iniziale', value=0.0))
            session.commit()
    except Exception as e:
        print(f"Error during init_db: {e}")
        session.rollback()
    finally:
        session.close()

def get_session():
    return Session()

def add_trade(trade_data):
    session = get_session()
    new_trade = TradingLog(**trade_data)
    session.add(new_trade)
    session.commit()
    session.close()

def update_trade(trade_id, update_data):
    session = get_session()
    session.query(TradingLog).filter(TradingLog.id == trade_id).update(update_data)
    session.commit()
    session.close()

def delete_trade(trade_id):
    session = get_session()
    session.query(TradingLog).filter(TradingLog.id == trade_id).delete()
    session.commit()
    session.close()

def get_all_trades():
    session = get_session()
    trades = session.query(TradingLog).all()
    session.close()
    return trades

def get_trades_df():
    # Helper to get data as pandas DataFrame for Streamlit
    # engine = create_engine(f'sqlite:///{DB_NAME}')
    return pd.read_sql('trading_log', engine)

def get_initial_balance():
    session = Session()
    setting = session.query(PortfolioSettings).filter_by(key='saldo_iniziale').first()
    val = setting.value if setting else 0.0
    session.close()
    return val

def update_initial_balance(new_val):
    session = Session()
    setting = session.query(PortfolioSettings).filter_by(key='saldo_iniziale').first()
    if setting:
        setting.value = new_val
    else:
        session.add(PortfolioSettings(key='saldo_iniziale', value=new_val))
    session.commit()
    session.close()

if __name__ == "__main__":
    init_db()
    print("Database initialized.")
