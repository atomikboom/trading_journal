import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timezone
import os
from dotenv import load_dotenv, set_key

load_dotenv(override=True)

from database import (init_db, add_trade, get_trades_df, update_trade, 
                      get_session, TradingLog, get_initial_balance, 
                      update_initial_balance, delete_trade)
from api import get_current_price, resolve_isin_to_symbol
from calculations import (calculate_metrics, get_calculated_values, 
                        get_portfolio_performance_metrics, get_risk_analysis,
                        get_tax_wallet_summary)

# Page Config
st.set_page_config(page_title="Automatic Trading Journal", layout="wide", page_icon="📈")

# Initialize DB
init_db()

# --- Authentication ---
if 'authenticated' not in st.session_state:
    st.session_state['authenticated'] = False
    st.session_state['role'] = None

def login():
    st.title("🔐 Login Portfolio Tracker")
    with st.form("login_form"):
        user = st.text_input("Username")
        pwd = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Accedi")
        if submitted:
            if (user == "admin" and pwd == "admin123") or (user == "viewer" and pwd == "viewer123"):
                st.session_state['authenticated'] = True
                st.session_state['role'] = user
                st.rerun()
            else:
                st.error("Credenziali non valide.")

if not st.session_state['authenticated']:
    login()
    st.stop()

# --- Custom CSS ---
st.markdown("""
<style>
    .main { background-color: #0e1117; }
    .stMetric {
        background-color: #1e2130;
        padding: 15px;
        border-radius: 10px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    .stTable { border-radius: 10px; }
    h1, h2, h3 { color: #00d4ff; }
    .active-trade-card {
        background-color: #1e2130;
        padding: 10px;
        border-radius: 5px;
        margin-bottom: 10px;
        border-left: 5px solid #00d4ff;
    }
    .tax-positive { color: #2ecc71; font-weight: bold; }
    .tax-negative { color: #e74c3c; font-weight: bold; }
    .zainetto-card {
        background-color: #161b22;
        padding: 20px;
        border-radius: 10px;
        border: 1px solid #30363d;
    }
</style>
""", unsafe_allow_html=True)

# Helper function to update all open prices
def update_all_prices():
    session = get_session()
    open_trades = session.query(TradingLog).filter(TradingLog.stato == 'APERTA').all()
    
    if not open_trades:
        st.info("Nessuna operazione aperta da aggiornare.")
        session.close()
        return

    progress_bar = st.progress(0)
    errors = []
    
    for i, trade in enumerate(open_trades):
        price, error = get_current_price(trade.strumento, trade.isin)
        if price:
            trade.prezzo_attuale = price
            calculate_metrics(trade)
        else:
            errors.append(f"{trade.strumento or trade.isin}: {error}")
        progress_bar.progress((i + 1) / len(open_trades))
    
    session.commit()
    session.close()
    
    if not errors:
        st.success("Tutti i prezzi sono stati aggiornati!")
    else:
        st.warning("Alcuni aggiornamenti sono falliti:")
        with st.expander("Dettagli errori"):
            for err in errors:
                st.error(err)

# --- Sidebar ---
st.sidebar.title(f"👤 {st.session_state['role'].capitalize()}")
if st.sidebar.button("Logout"):
    st.session_state['authenticated'] = False
    st.rerun()

st.sidebar.divider()

# Capital Management
st.sidebar.title("💰 Gestione Capitale")
initial_balance = get_initial_balance()
new_balance = st.sidebar.number_input("Saldo Iniziale / Versamenti (€)", value=float(initial_balance), step=100.0)
if st.sidebar.button("Aggiorna Saldo"):
    update_initial_balance(new_balance)
    st.sidebar.success("Saldo aggiornato!")
    st.rerun()

st.sidebar.divider()
st.sidebar.title("⚙️ Configurazioni")
api_key = st.sidebar.text_input("AlphaVantage API Key", value=os.getenv("ALPHAVANTAGE_API_KEY", ""), type="password")

if st.sidebar.button("Salva API Key"):
    set_key(".env", "ALPHAVANTAGE_API_KEY", api_key)
    st.sidebar.success("API Key salvata!")
    st.rerun()

if st.sidebar.button("🔄 Aggiorna Prezzi Live"):
    update_all_prices()

# Load data
df = get_trades_df()

# --- Main App ---
st.title("📈 Automatic Trading Journal")
tabs = st.tabs(["📊 Dashboard", "📝 Operazioni", "➕ Nuova Posizione", "🧮 Calcolatore TP/SL"])

# --- Dashboard Tab ---
with tabs[0]:
    if df.empty:
        st.subheader("💰 Saldo Iniziale")
        st.metric("Capitale Totale", f"€ {initial_balance:,.2f}")
        st.info("Nessun dato sulle operazioni disponibile.")
    else:
        # 1. Performance Metrics
        perf = get_portfolio_performance_metrics(df)
        risk = get_risk_analysis(df)
        tax_summary = get_tax_wallet_summary(df)
        
        st.subheader("🚀 Portafoglio Performance")
        p_cols = st.columns(4)
        p_cols[0].metric("Mensile", f"{perf.get('Monthly', 0):.2f} %")
        p_cols[1].metric("YTD", f"{perf.get('YTD', 0):.2f} %")
        p_cols[2].metric("LTM (12m)", f"{perf.get('LTM', 0):.2f} %")
        p_cols[3].metric("Inception", f"{perf.get('Inception', 0):.2f} %")

        st.divider()
        
        # 2. Key Metrics & Zainetto Fiscale
        m_cols = st.columns([2, 1])
        with m_cols[0]:
            st.subheader("💰 Asset & Profit")
            sub_cols = st.columns(3)
            current_value = df['valore_attuale'].sum()
            total_profit = df['net_profit'].sum()
            total_equity = initial_balance + total_profit
            
            sub_cols[0].metric("Saldo Iniziale", f"€ {initial_balance:,.2f}")
            sub_cols[1].metric("Profitto Netto", f"€ {total_profit:,.2f}", delta=f"{total_profit:,.2f}")
            sub_cols[2].metric("Capitale Attuale", f"€ {total_equity:,.2f}", delta=f"{((total_equity/initial_balance)-1)*100:.2f} %" if initial_balance > 0 else None)
        
        with m_cols[1]:
            st.subheader("💼 Zainetto Fiscale")
            with st.container():
                st.markdown(f"""
                <div class="zainetto-card">
                    Plusvalenze Realizzate: <span class="tax-positive">€ {tax_summary['Plusvalenze Totali']:.2f}</span><br>
                    Minusvalenze Realizzate: <span class="tax-negative">€ {tax_summary['Minusvalenze Totali']:.2f}</span><br>
                    <hr style="margin: 10px 0; border-color: #30363d;">
                    Bilancio Fiscale: <span class="{'tax-positive' if tax_summary['Bilancio Fiscale'] >= 0 else 'tax-negative'}">€ {tax_summary['Bilancio Fiscale']:.2f}</span><br>
                    Tasse Pagate/Dovute: <span class="tax-negative">€ {tax_summary['Total Taxes Paid']:.2f}</span>
                </div>
                """, unsafe_allow_html=True)

        st.divider()

        # 3. Graphs
        st.subheader("📈 Analisi Grafica")
        g_cols = st.columns(2)
        with g_cols[0]:
            st.subheader("Portfolio Equity Curve (Cumulative)")
            df_sorted = df.sort_values('data_operazione').copy()
            df_sorted['cum_profit'] = df_sorted['net_profit'].cumsum()
            df_sorted['equity'] = initial_balance + df_sorted['cum_profit']
            fig_equity = px.line(df_sorted, x='data_operazione', y='equity', 
                                title="Andamento Capitale Totale",
                                template="plotly_dark", color_discrete_sequence=['#00d4ff'])
            st.plotly_chart(fig_equity, use_container_width=True)
            
        with g_cols[1]:
            st.subheader("Monthly Profit/Loss (Realized)")
            df_closed = df[df['stato'] == 'CHIUSA'].copy()
            if not df_closed.empty:
                df_closed['data_operazione'] = pd.to_datetime(df_closed['data_operazione'])
                df_monthly = df_closed.set_index('data_operazione').resample('ME')['plus_minus'].sum().reset_index()
                df_monthly['data_operazione'] = df_monthly['data_operazione'].dt.strftime('%b %Y')
                fig_monthly = px.bar(df_monthly, x='data_operazione', y='plus_minus', 
                                    color='plus_minus', color_continuous_scale=['#e74c3c', '#2ecc71'],
                                    template="plotly_dark", title="Profitto/Perdita per Mese")
                st.plotly_chart(fig_monthly, use_container_width=True)
            else:
                st.info("Nessuna chiusura presente per il grafico mensile.")

        # 4. Allocation Details
        st.divider()
        st.subheader("⚖️ Allocazione Asset")
        a_cols = st.columns(2)
        with a_cols[0]:
            fig_curr = px.pie(df, names='valuta', values='valore_attuale', hole=0.4, title="Per Valuta", template="plotly_dark")
            st.plotly_chart(fig_curr, use_container_width=True)
        with a_cols[1]:
            fig_cat = px.pie(df, names='categoria', values='valore_attuale', hole=0.4, title="Per Categoria", template="plotly_dark")
            st.plotly_chart(fig_cat, use_container_width=True)

        st.divider()

        # 5. Active Trades List
        st.subheader("📂 Trade Attivi")
        active_df = df[df['stato'] == 'APERTA'].copy()
        if not active_df.empty:
            for _, row in active_df.iterrows():
                with st.container():
                    st.markdown(f"""
                    <div class="active-trade-card">
                        <div style="display: flex; justify-content: space-between;">
                            <span><b>{row['strumento']}</b> ({row['isin']}) - {row['categoria']}</span>
                            <span>Valuta: {row['valuta']}</span>
                        </div>
                        <div style="margin-top: 5px; font-size: 0.9em;">
                            Qta: {row['quantità']} | 
                            PMC (incl. fee): € {row['prezzo_medio_carico'] if row['prezzo_medio_carico'] else row['prezzo_entrata']:.2f} | 
                            Prezzo Attuale: € {row['prezzo_attuale']:.2f}
                        </div>
                        <div style="margin-top: 5px;">
                            P/L Lordo: <span style="color:{'#2ecc71' if row['plus_minus'] > 0 else '#e74c3c'}">€ {row['plus_minus']:.2f}</span> | 
                            Rendimento Netto: <span style="color:{'#2ecc71' if row['rendimento_percentuale'] > 0 else '#e74c3c'}">{row['rendimento_percentuale']:.2f}%</span> |
                            Tasse Latenti (26%): € {row['tassazione']:.2f}
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
        else:
            st.write("Nessun trade attivo.")

# --- Operations Tab ---
with tabs[1]:
    if not df.empty:
        st.subheader("⚙️ Gestione Portafoglio")
        
        # Use a more descriptive selectbox
        df_all = df.copy()
        df_all['display_name'] = df_all['strumento'] + " (" + df_all['data_operazione'].astype(str) + ")"
        
        selected_trade_id = st.selectbox("Seleziona Operazione (ID)", df_all['id'].tolist(), format_func=lambda x: f"ID {x}: {df_all[df_all['id']==x]['display_name'].iloc[0]}")
        selected_row = df_all[df_all['id'] == selected_trade_id].iloc[0]

        op_tabs = st.tabs(["📝 Modifica / Azioni", "🗑️ Elimina"])
        
        with op_tabs[0]:
            if st.session_state['role'] == 'admin':
                col_left, col_right = st.columns(2)
                
                with col_left:
                    st.markdown("##### Dati Principali")
                    with st.form(f"edit_main_{selected_trade_id}"):
                        e_sym = st.text_input("Ticker", value=selected_row['strumento'])
                        e_isin = st.text_input("ISIN", value=selected_row['isin'] or "")
                        e_qta = st.number_input("Quantità", value=float(selected_row['quantità']))
                        e_pmc = st.number_input("PMC", value=float(selected_row['prezzo_medio_carico'] or selected_row['prezzo_entrata']))
                        if st.form_submit_button("Salva Dati Base"):
                            session = get_session()
                            t = session.query(TradingLog).filter_by(id=int(selected_trade_id)).first()
                            t.strumento = e_sym.upper(); t.isin = e_isin.upper()
                            t.quantità = e_qta; t.prezzo_medio_carico = e_pmc; t.prezzo_entrata = e_pmc
                            calculate_metrics(t); session.commit(); session.close()
                            st.success("Dati aggiornati!"); st.rerun()

                with col_right:
                    if selected_row['stato'] == 'APERTA':
                        st.markdown("##### Chiudi Operazione")
                        with st.form(f"close_trade_{selected_trade_id}"):
                            max_q = float(selected_row['quantità'])
                            s_qta = st.number_input("Qta da vendere", min_value=0.0001, max_value=max_q, value=max_q)
                            exit_p = st.number_input("Prezzo Uscita", value=float(selected_row['prezzo_attuale'] or selected_row['prezzo_entrata']))
                            fee_out = st.number_input("Costi Chiusura (€)", value=2.95)
                            if st.form_submit_button("Conferma Vendita"):
                                session = get_session()
                                t = session.query(TradingLog).filter_by(id=int(selected_trade_id)).first()
                                if s_qta < max_q:
                                    # Parziale
                                    new_c = TradingLog(
                                        data_operazione=t.data_operazione, strumento=t.strumento, isin=t.isin,
                                        tipologia=t.tipologia, categoria=t.categoria, valuta=t.valuta,
                                        quantità=s_qta, prezzo_entrata=t.prezzo_entrata, prezzo_medio_carico=t.prezzo_medio_carico,
                                        prezzo_uscita=exit_p, costi_apertura=(t.costi_apertura/max_q)*s_qta,
                                        costi_chiusura=fee_out, costo_mantenimento_annuo=t.costo_mantenimento_annuo, stato='CHIUSA'
                                    )
                                    t.quantità -= s_qta; t.costi_apertura -= (t.costi_apertura/max_q)*s_qta
                                    calculate_metrics(t); calculate_metrics(new_c); session.add(new_c)
                                else:
                                    t.stato='CHIUSA'; t.prezzo_uscita=exit_p; t.costi_chiusura=fee_out
                                    calculate_metrics(t)
                                session.commit(); session.close()
                                st.success("Trade chiuso!"); st.rerun()
                    else:
                        st.info("Questa operazione è già chiusa.")
            else:
                st.warning("Solo gli admin possono modificare le operazioni.")

        with op_tabs[1]:
            if st.session_state['role'] == 'admin':
                st.warning(f"⚠️ ATTENZIONE: Sei sicuro di voler eliminare l'operazione ID {selected_trade_id}?")
                st.write("Questa azione è irreversibile.")
                if st.button(f"🔴 CONFERMA ELIMINAZIONE ID {selected_trade_id}", key=f"del_{selected_trade_id}"):
                    delete_trade(int(selected_trade_id))
                    st.toast(f"Operazione {selected_trade_id} eliminata con successo!")
                    st.rerun()
            else:
                st.warning("Solo gli amministratori possono eliminare le operazioni.")

        st.divider()
        st.subheader("📋 Tutte le Operazioni")
        st.dataframe(df[['id', 'data_operazione', 'strumento', 'categoria', 'stato', 'quantità', 'prezzo_medio_carico', 'prezzo_attuale', 'net_profit', 'rendimento_percentuale']].style.format(precision=2), hide_index=True)
    else:
        st.info("Nessuna operazione registrata.")

# --- Insert Tab ---
with tabs[2]:
    if st.session_state['role'] == 'admin':
        st.subheader("🆕 Inserimento Nuova Posizione")
        with st.form("new_trade_form_v2"):
            c1, c2, c3 = st.columns(3)
            date_op = c1.date_input("Data", datetime.now(timezone.utc).replace(tzinfo=None))
            symbol = c2.text_input("Ticker").upper()
            isin = c3.text_input("ISIN").upper()
            
            c4, c5, c6 = st.columns(3)
            cat = c4.selectbox("Categoria", ["Azioni", "Certificati", "ETF", "Obbligazioni", "Crypto", "Altro"])
            val = c5.selectbox("Valuta", ["EUR", "USD", "GBP", "CHF"])
            qta = c6.number_input("Quantità", min_value=0.0, step=0.1)
            
            c7, c8, c9 = st.columns(3)
            pmc = c7.number_input("Prezzo Medio di Carico", min_value=0.0)
            fee_in = c8.number_input("Costi Apertura (€)", value=2.95)
            maint_ann = c9.number_input("Mantenimento Annuo (%)", value=0.20)
            
            note = st.text_area("Note (opzionale)")
            
            if st.form_submit_button("✅ Aggiungi Operazione"):
                # Fetch price if possible
                price, err = get_current_price(symbol, isin)
                trade_data = {
                    'data_operazione': datetime.combine(date_op, datetime.min.time()),
                    'strumento': symbol, 'isin': isin, 'categoria': cat, 'valuta': val,
                    'quantità': qta, 'prezzo_entrata': pmc, 'prezzo_medio_carico': pmc,
                    'prezzo_attuale': price if price else pmc,
                    'costi_apertura': fee_in, 'costo_mantenimento_annuo': maint_ann,
                    'stato': 'APERTA', 'note': note
                }
                session = get_session()
                new_t = TradingLog(**trade_data)
                calculate_metrics(new_t)
                session.add(new_t); session.commit(); session.close()
                st.success("Nuova posizione inserita!"); st.rerun()
    else:
        st.warning("Solo gli amministratori possono inserire nuove posizioni.")

# --- TP/SL Calculator Tab ---
with tabs[3]:
    st.subheader("🧮 Calcolatore Target Price & Stop Loss")
    
    # Input Section
    with st.container():
        c1, c2, c3 = st.columns(3)
        buy_price = c1.number_input("Prezzo di Acquisto", min_value=0.0001, value=10.00, step=0.01, format="%.4f")
        quantity = c2.number_input("Quantità di Acquisto", min_value=0.0001, value=100.0, step=1.0)
        total_investment = buy_price * quantity
        c3.metric("Investimento Totale", f"€ {total_investment:,.2f}")
        
        c4, c5, c6 = st.columns(3)
        entry_cost = c4.number_input("Costo di Entrata (€)", min_value=0.0, value=2.95, step=0.05)
        exit_cost = c5.number_input("Costo di Uscita (€)", min_value=0.0, value=2.95, step=0.05)
        
        st.divider()
        
        # Range Configuration
        st.markdown("##### ⚙️ Configurazione Range Tabella")
        r1, r2, r3 = st.columns(3)
        down_range = r1.number_input("Diminuzione Prezzo (range)", min_value=0.0, value=1.0, step=0.1)
        up_range = r2.number_input("Aumento Prezzo (range)", min_value=0.0, value=2.0, step=0.1)
        step_val = r3.number_input("Step di variazione", min_value=0.0001, value=0.05, step=0.01, format="%.4f")

    # Calculation Logic
    import numpy as np
    
    start_p = max(0.0001, buy_price - down_range)
    end_p = buy_price + up_range
    
    # Generate sequence including the exact buy_price, handled with precision
    prices = np.arange(start_p, end_p + step_val, step_val)
    # Append buy_price, round to handle float precision, and take unique values
    prices = np.unique(np.round(np.append(prices, buy_price), 4))
    # Sort just in case np.unique didn't maintain order (it usually does but safety first)
    prices = np.sort(prices)
    
    calc_data = []
    for p in prices:
        pl_perc = (p / buy_price) - 1
        pl_euro = (p - buy_price) * quantity - entry_cost - exit_cost
        taxes = max(0, pl_euro * 0.26) if pl_euro > 0 else 0
        net_profit = pl_euro - taxes
        
        calc_data.append({
            "Prezzo": p,
            "PL %": pl_perc,
            "PL €": pl_euro,
            "Tasse (26%)": taxes,
            "Profitto Netto": net_profit
        })
    
    calc_df = pd.DataFrame(calc_data)
    
    # --- Visualizations ---
    st.subheader("📊 Analisi Grafica Scenari")
    g_cols = st.columns(2)
    
    with g_cols[0]:
        st.markdown("##### 📈 Grafico di Payoff (Netto)")
        fig_payoff = px.line(calc_df, x="Prezzo", y="Profitto Netto", 
                             template="plotly_dark",
                             labels={"Prezzo": "Prezzo (€)", "Profitto Netto": "Profitto (€)"},
                             color_discrete_sequence=['#00d4ff'])
        fig_payoff.add_hline(y=0, line_dash="dash", line_color="gray")
        fig_payoff.add_vline(x=buy_price, line_dash="dot", line_color="#f1c40f")
        fig_payoff.update_traces(mode='lines+markers', marker=dict(size=4))
        st.plotly_chart(fig_payoff, use_container_width=True)

    with g_cols[1]:
        st.markdown("##### 📉 Performance Percentuale (PL %)")
        # Color bars based on positive/negative
        calc_df['color'] = calc_df['PL %'].apply(lambda x: '#2ecc71' if x > 0 else '#e74c3c')
        fig_pl = px.bar(calc_df, x="Prezzo", y="PL %",
                        template="plotly_dark",
                        labels={"Prezzo": "Prezzo (€)", "PL %": "Rendimento (%)"},
                        color='color', color_discrete_map="identity")
        fig_pl.add_hline(y=0, line_color="white", line_width=1)
        fig_pl.add_vline(x=buy_price, line_dash="dot", line_color="#f1c40f")
        # Format Y axis as percentage
        fig_pl.update_layout(yaxis_tickformat='.1%')
        st.plotly_chart(fig_pl, use_container_width=True)

    # Display Table with Formatting
    st.subheader("📋 Tabella Riepilogativa Scenari")
    
    def highlight_buy_price(s):
        is_buy = s.Prezzo == buy_price
        return ['background-color: #1e3a5f; font-weight: bold' if is_buy else '' for _ in s]

    def color_pl(val):
        color = '#2ecc71' if val > 0 else '#e74c3c' if val < 0 else 'white'
        return f'color: {color}'

    styled_df = calc_df.style.format({
        "Prezzo": "{:.4f}",
        "PL %": "{:.2%}",
        "PL €": "€ {:.2f}",
        "Tasse (26%)": "€ {:.2f}",
        "Profitto Netto": "€ {:.2f}"
    }).apply(highlight_buy_price, axis=1)\
      .map(color_pl, subset=['PL %', 'PL €', 'Profitto Netto'])

    st.dataframe(styled_df, use_container_width=True, height=600, hide_index=True)

st.sidebar.markdown("---")
st.sidebar.caption("Automatic Trading Journal v2.5")
st.sidebar.caption("Developed by Antigravity")
