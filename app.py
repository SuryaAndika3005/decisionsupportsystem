import streamlit as st
import pandas as pd
import numpy as np
import joblib
import datetime
import requests
import plotly.express as px

# 1. KONFIGURASI HALAMAN
st.set_page_config(
    page_title="Sistem Prediksi Stok Bahan",
    page_icon="📦",
    layout="wide"
)

# Konstanta Tetap & Penyesuaian Skala Lokal
GALON_TO_LITER = 3.78541
HARGA_BBM_IDR_LITER = 13500  
SKALA_LOKAL = 0.001 

# 2. FUNGSI LOAD DATA & LIVE API
@st.cache_resource
def load_model():
    try:
        return joblib.load('walmart_rf_model.pkl')
    except FileNotFoundError:
        return None

@st.cache_data
def load_data():
    try:
        df = pd.read_csv('Walmart.csv')
        df['Date'] = pd.to_datetime(df['Date'], format='%d-%m-%Y')
        return df
    except FileNotFoundError:
        return None

@st.cache_data(ttl=3600)
def get_live_usd_idr():
    try:
        response = requests.get('https://api.exchangerate-api.com/v4/latest/USD', timeout=5)
        return response.json()['rates']['IDR']
    except:
        return 16000.0  

model = load_model()
df = load_data()
live_kurs = get_live_usd_idr()

if df is None or model is None:
    st.error("❌ Pastikan 'Walmart.csv' dan 'walmart_rf_model.pkl' berada di folder yang sama.")
    st.stop()

# --- MAPPING DATA TOKO MENJADI NAMA BAHAN PERABOT ---
daftar_id_asli = sorted(df['Store'].unique())
daftar_barang_ui = []

for i in daftar_id_asli:
    if i == 1: nama = "Busa Lembaran Super (ID: 1)"
    elif i == 2: nama = "Kain Katun Motif (ID: 2)"
    elif i == 3: nama = "Kain Oscar Sintetis (ID: 3)"
    elif i == 4: nama = "Dakron Kiloan (ID: 4)"
    elif i == 5: nama = "Busa Rebonded (ID: 5)"
    else: nama = f"Bahan Perabot Lainnya (ID: {i})"
    daftar_barang_ui.append(nama)

# 3. SIDEBAR 
st.sidebar.header("🎯 Pemilihan Material")
selected_item_str = st.sidebar.selectbox("Pilih Material/Barang:", daftar_barang_ui, index=0)
selected_item_id = int(selected_item_str.split("(ID: ")[1].replace(")", ""))

st.sidebar.divider()
st.sidebar.header("📡 Live Market Data")
st.sidebar.info(
    f"**Kurs USD Saat Ini:**\nRp {live_kurs:,.0f} / 1 USD\n\n"
    f"**Harga BBM Referensi:**\nRp {HARGA_BBM_IDR_LITER:,.0f} / Liter"
)

store_data = df[df['Store'] == selected_item_id].sort_values('Date')

# 4. HEADER UTAMA
st.title("📦 Sistem Manajemen & Peramalan Stok Bahan Perabot")
st.markdown("Analisis pergerakan inventaris dan simulasikan ketahanan stok di gudang minggu demi minggu untuk mencegah kekosongan material.")
st.divider()

tab1, tab2 = st.tabs(["🤖 Panel Simulasi & Ketahanan Stok", "📈 Riwayat Pergerakan Barang"])

cuaca_mapping = {
    "🌧️ Dingin / Hujan Lebat": 45.0,
    "☁️ Sejuk / Mendung": 65.0,
    "⛅ Hangat / Cerah Berawan": 80.0,
    "☀️ Panas / Terik": 95.0
}

# ==========================================
# TAB 1: PANEL PREDIKSI & KEPUTUSAN 
# ==========================================
with tab1:
    st.subheader(f"📋 Pengecekan Logistik: {selected_item_str.split(' (')[0]}")
    
    with st.form("inventory_prediction_form"):
        col1, col2, col3 = st.columns(3)
        with col1:
            target_date = st.date_input("📅 Tanggal Awal Pengecekan", datetime.date.today())
        with col2:
            holiday_select = st.selectbox("🎉 Status Hari Libur", ["Bukan Hari Libur", "Ada Hari Libur Nasional"])
            sim_holiday_flag = 1 if holiday_select == "Ada Hari Libur Nasional" else 0
        with col3:
            cuaca_select = st.selectbox("🌤️ Perkiraan Cuaca Awal", list(cuaca_mapping.keys()))
            
        st.markdown("---")
        st.markdown("**🛒 Profil & Status Barang di Gudang**")
        
        col_stok1, col_stok2 = st.columns(2)
        with col_stok1:
            harga_rata_barang = st.number_input("Harga Dasar Barang (Rp/Unit)", min_value=1000, value=150000, step=5000)
        with col_stok2:
            stok_saat_ini = st.number_input("Jumlah Fisik Stok di Gudang Saat Ini (Unit)", min_value=0, value=450, step=10)

        submit_btn = st.form_submit_button("Analisis Pergerakan Stok", type="primary", use_container_width=True)

    if submit_btn:
        sim_temp_f = cuaca_mapping[cuaca_select]
        sim_fuel_usd_gal = (HARGA_BBM_IDR_LITER / live_kurs) * GALON_TO_LITER
        sim_cpi = float(store_data['CPI'].mean())
        sim_unemp = float(store_data['Unemployment'].mean())
        
        st.markdown("<br>", unsafe_allow_html=True)
        st.subheader("⏳ Proyeksi Ketahanan Stok (Run-Out Analysis)")

        stok_berjalan = stok_saat_ini
        tanggal_berjalan = target_date
        tabel_proyeksi = []
        
        for i in range(1, 13): 
            df_simulasi = pd.DataFrame({
                'Store': [selected_item_id], 
                'Holiday_Flag': [sim_holiday_flag if i == 1 else 0], 
                'Temperature': [sim_temp_f], 'Fuel_Price': [sim_fuel_usd_gal],
                'CPI': [sim_cpi], 'Unemployment': [sim_unemp],
                'Day': [tanggal_berjalan.day], 'Month': [tanggal_berjalan.month], 
                'Year': [tanggal_berjalan.year], 'Week': [tanggal_berjalan.isocalendar().week]
            })
            
            pred_usd = model.predict(df_simulasi)[0]
            pred_idr = (pred_usd * live_kurs) * SKALA_LOKAL
            kebutuhan_unit = int(pred_idr / harga_rata_barang)
            
            sisa_akhir = stok_berjalan - kebutuhan_unit
            status = "✅ Aman" if sisa_akhir > 0 else "❌ Habis (Stockout)"
            
            tabel_proyeksi.append({
                "Minggu Ke-": i,
                "Periode Tanggal": tanggal_berjalan.strftime("%d %b %Y"),
                "Estimasi Permintaan (Unit)": kebutuhan_unit,
                "Sisa Stok Akhir (Unit)": sisa_akhir if sisa_akhir > 0 else 0,
                "Status Gudang": status
            })
            
            if sisa_akhir <= 0:
                break 
                
            stok_berjalan = sisa_akhir
            tanggal_berjalan += datetime.timedelta(days=7) 
            
        df_hasil = pd.DataFrame(tabel_proyeksi)
        st.dataframe(df_hasil, use_container_width=True, hide_index=True)
        
        # --- FITUR TAMBAHAN: UNDUH LAPORAN CSV ---
        csv_data = df_hasil.to_csv(index=False).encode('utf-8')
        nama_file_csv = f"Proyeksi_Stok_{selected_item_str.split(' (')[0].replace(' ', '_')}.csv"
        
        st.download_button(
            label="📥 Unduh Laporan Proyeksi (CSV)",
            data=csv_data,
            file_name=nama_file_csv,
            mime="text/csv",
        )
        
        st.markdown("### 📋 Kesimpulan & Rekomendasi Manajerial")
        minggu_bertahan = len(df_hasil)
        kebutuhan_minggu_1 = df_hasil.iloc[0]["Estimasi Permintaan (Unit)"]

        if minggu_bertahan == 1 and sisa_akhir <= 0:
            st.error(f"🚨 **KRITIS:** Stok sebesar {stok_saat_ini} unit **tidak cukup** untuk memenuhi permintaan minggu ini (Estimasi: {kebutuhan_minggu_1} unit). Segera lakukan *restock* kilat!")
        elif minggu_bertahan < 4:
            st.warning(f"⚠️ **MENIPIS:** Stok diproyeksikan akan **habis dalam {minggu_bertahan} minggu**. Lakukan pemesanan barang ke *supplier* sekarang agar barang tiba sebelum {df_hasil.iloc[-1]['Periode Tanggal']}.")
        else:
            st.success(f"🛡️ **SANGAT AMAN:** Ketahanan stok sangat baik. Gudang diproyeksikan baru akan kosong setelah **{minggu_bertahan} minggu**. Tidak perlu re-stok dalam waktu dekat.")


# ==========================================
# TAB 2: RIWAYAT TREN PENJUALAN DENGAN GARIS AMAN
# ==========================================
with tab2:
    st.subheader(f"📈 Riwayat Estimasi Perputaran {selected_item_str.split(' (')[0]}")
    
    col_grafik1, col_grafik2 = st.columns(2)
    with col_grafik1:
        asumsi_harga_grafik = st.number_input("Asumsi harga per unit (Rp):", min_value=1000, value=150000, step=5000)
    with col_grafik2:
        # --- FITUR TAMBAHAN: INPUT BATAS SAFETY STOCK ---
        batas_aman_stok = st.number_input("Tentukan Batas Kritis / Safety Stock (Unit):", min_value=0, value=50, step=10, help="Garis merah putus-putus akan muncul di grafik sebagai batas peringatan.")
    
    chart_data = store_data.copy()
    chart_data['Pendapatan (Rupiah)'] = (chart_data['Weekly_Sales'] * live_kurs) * SKALA_LOKAL
    chart_data['Perkiraan Volume (Unit)'] = chart_data['Pendapatan (Rupiah)'] / asumsi_harga_grafik
    
    fig_time = px.line(
        chart_data, x='Date', y='Perkiraan Volume (Unit)',
        labels={'Perkiraan Volume (Unit)': 'Total Unit Keluar', 'Date': 'Periode'},
        template='plotly_white'
    )
    
    # --- FITUR TAMBAHAN: GARIS BATAS AMAN (HORIZONTAL LINE) ---
    fig_time.add_hline(
        y=batas_aman_stok, 
        line_dash="dash", 
        line_color="red", 
        annotation_text="Batas Kritis (Safety Stock)", 
        annotation_position="bottom right"
    )
    
    fig_time.update_layout(hovermode="x unified")
    st.plotly_chart(fig_time, use_container_width=True)