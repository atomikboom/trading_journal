import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone

def calculate_metrics(trade):
    """
    Perform financial calculations for a single trade based on its status.
    Modifies the trade object in-place.
    
    Logic updated:
    - Costo Mantenimento = (Investito Lordo * % Annua / 365) * Giorni Detenzione
    - Investito Netto (Totale) = Investito Lordo + Costi Apertura + Costo Mantenimento
    """
    pmc = trade.prezzo_medio_carico if trade.prezzo_medio_carico else trade.prezzo_entrata
    
    # 1. Investito Lordo = Quantità * PMC
    trade.investito_lordo = trade.quantità * pmc
    
    # 2. Calcolo Giorni Detenzione
    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    date_end = now_utc if trade.stato == 'APERTA' else trade.data_operazione
    
    start_date = trade.data_operazione
    end_date = now_utc # Default for open
    
    days_held = max(1, (end_date - start_date).days)
    
    # 3. Costo Mantenimento (Proratato)
    ann_rate = getattr(trade, 'costo_mantenimento_annuo', 0.20) / 100
    maint_cost = (trade.investito_lordo * ann_rate / 365.0) * days_held
    
    # 4. Investito Netto (si arricchisce col mantenimento)
    trade.investito_netto = trade.investito_lordo + trade.costi_apertura + maint_cost
    
    if trade.stato == 'APERTA':
        prezzo_rif = trade.prezzo_attuale if trade.prezzo_attuale else pmc
        trade.valore_attuale = trade.quantità * prezzo_rif
        trade.plus_minus = trade.valore_attuale - trade.investito_netto
        
        if trade.plus_minus > 0:
            trade.tassazione = trade.plus_minus * 0.26
        else:
            trade.tassazione = 0.0
            
        trade.net_profit = trade.plus_minus - trade.tassazione
        
    else:  # CHIUSA
        if trade.prezzo_uscita is None:
            trade.prezzo_uscita = pmc
            
        trade.valore_attuale = (trade.quantità * trade.prezzo_uscita) - trade.costi_chiusura
        trade.plus_minus = trade.valore_attuale - trade.investito_netto
        
        if trade.plus_minus > 0:
            trade.tassazione = trade.plus_minus * 0.26
        else:
            trade.tassazione = 0.0
            
        trade.net_profit = trade.plus_minus - trade.tassazione
        
    if trade.investito_netto > 0:
        trade.rendimento_percentuale = (trade.net_profit / trade.investito_netto) * 100
    else:
        trade.rendimento_percentuale = 0.0
    
    return trade

def get_tax_wallet_summary(df):
    """
    Calculate the 'Zainetto Fiscale' (Tax Wallet) metrics.
    Accumulates realized gains and losses.
    """
    closed_df = df[df['stato'] == 'CHIUSA']
    if closed_df.empty:
        return {
            "Total Realized P/L": 0.0,
            "Total Taxes Paid": 0.0,
            "Plusvalenze Totali": 0.0,
            "Minusvalenze Totali": 0.0,
            "Bilancio Fiscale": 0.0
        }
    
    realized_pl = closed_df['plus_minus'].sum()
    taxes_paid = closed_df['tassazione'].sum()
    
    # Minusvalenze are negative P/L
    minusvalenze = abs(closed_df[closed_df['plus_minus'] < 0]['plus_minus'].sum())
    # Plusvalenze are positive P/L
    plusvalenze = closed_df[closed_df['plus_minus'] > 0]['plus_minus'].sum()
    
    return {
        "Total Realized P/L": realized_pl,
        "Total Taxes Paid": taxes_paid,
        "Plusvalenze Totali": plusvalenze,
        "Minusvalenze Totali": minusvalenze,
        "Bilancio Fiscale": plusvalenze - minusvalenze
    }

def get_portfolio_performance_metrics(df):
    """
    Calculate performance metrics: Monthly, YTD, LTM, Inception.
    """
    if df.empty:
        return {}
    
    df['data_operazione'] = pd.to_datetime(df['data_operazione'])
    now = datetime.now()
    
    # Helper to calculate return for a period
    def calc_period_return(df_period):
        if df_period.empty: return 0.0
        invested = df_period['investito_netto'].sum()
        profit = df_period['net_profit'].sum()
        return (profit / invested * 100) if invested > 0 else 0.0

    # Monthly (last 30 days)
    month_ago = now - timedelta(days=30)
    monthly_ret = calc_period_return(df[df['data_operazione'] >= month_ago])
    
    # YTD
    year_start = datetime(now.year, 1, 1)
    ytd_ret = calc_period_return(df[df['data_operazione'] >= year_start])
    
    # LTM (Last Twelve Months)
    ltm_ago = now - timedelta(days=365)
    ltm_ret = calc_period_return(df[df['data_operazione'] >= ltm_ago])
    
    # Inception
    inception_ret = calc_period_return(df)
    
    return {
        "Monthly": monthly_ret,
        "YTD": ytd_ret,
        "LTM": ltm_ret,
        "Inception": inception_ret
    }

def get_risk_analysis(df, initial_balance):
    """
    Calculate risk metrics: Standard Deviation, Sharpe, Sortino, VaR, and Max Drawdown.
    """
    if df.empty:
        return {
            "StdDev": 0.0, "Sharpe": 0.0, "Sortino": 0.0, 
            "VaR": 0.0, "MaxDrawdown": 0.0, "CurrentDrawdown": 0.0
        }
    
    # Sort by date for time-series analysis
    df_sorted = df.sort_values('data_operazione').copy()
    returns = df_sorted['rendimento_percentuale'].fillna(0) / 100
    
    # 1. Std Dev & Variance
    std_dev = np.std(returns) if len(returns) > 1 else 0.0
    
    # 2. Sharpe Ratio (assuming 0% risk-free rate for simplicity)
    mean_ret = np.mean(returns)
    sharpe = (mean_ret / std_dev) if std_dev > 0 else 0.0
    
    # 3. Sortino Ratio
    downside_returns = returns[returns < 0]
    downside_std = np.std(downside_returns) if len(downside_returns) > 1 else 0.0
    sortino = (mean_ret / downside_std) if downside_std > 0 else 0.0
    
    # 4. Value at Risk (VaR) - 95% Confidence (Historical)
    if len(returns) >= 5:
        var_95 = np.percentile(returns, 5)
    else:
        var_95 = 0.0
        
    # 5. Drawdown Analysis
    df_sorted['cum_profit'] = df_sorted['net_profit'].cumsum()
    df_sorted['equity'] = initial_balance + df_sorted['cum_profit']
    df_sorted['peak'] = df_sorted['equity'].cummax()
    df_sorted['drawdown'] = (df_sorted['equity'] - df_sorted['peak']) / df_sorted['peak']
    
    max_drawdown = df_sorted['drawdown'].min() if not df_sorted.empty else 0.0
    current_drawdown = df_sorted['drawdown'].iloc[-1] if not df_sorted.empty else 0.0
    
    return {
        "StdDev": std_dev * 100, # In percentage
        "Sharpe": sharpe,
        "Sortino": sortino,
        "VaR": var_95 * 100, # In percentage
        "MaxDrawdown": max_drawdown * 100, # In percentage
        "CurrentDrawdown": current_drawdown * 100, # In percentage
        "EquityCurve": df_sorted[['data_operazione', 'equity', 'drawdown']].to_dict('records')
    }

def get_calculated_values(data):
    # (Leaving this for backward compatibility if needed, but updating to use PMC)
    qta = data.get('quantità', 0)
    pmc = data.get('prezzo_medio_carico', data.get('prezzo_entrata', 0))
    p_out = data.get('prezzo_uscita')
    p_curr = data.get('prezzo_attuale')
    costi_in = data.get('costi_apertura', 0)
    costi_out = data.get('costi_chiusura', 0)
    stato = data.get('stato', 'APERTA')
    
    inv_lordo = qta * pmc
    inv_netto = inv_lordo + costi_in
    
    if stato == 'APERTA':
        prezzo_rif = p_curr if p_curr is not None else pmc
        valore_attuale = qta * prezzo_rif
    else:
        valore_attuale = (qta * (p_out if p_out is not None else pmc)) - costi_out
        
    plus_minus = valore_attuale - inv_netto
    tassazione = max(0, plus_minus * 0.26)
    net_profit = plus_minus - tassazione
    rendimento = (net_profit / inv_netto * 100) if inv_netto > 0 else 0
    
    return {
        'investito_lordo': inv_lordo,
        'investito_netto': inv_netto,
        'valore_attuale': valore_attuale,
        'plus_minus': plus_minus,
        'tassazione': tassazione,
        'net_profit': net_profit,
        'rendimento_percentuale': rendimento
    }
