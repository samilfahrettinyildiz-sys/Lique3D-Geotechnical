import streamlit as st
import pandas as pd
import numpy as np
import re
from modules.hesap_motoru import geoteknik_analiz
from modules.cizim_motoru import ciz_spektrum, ciz_3d, ciz_2d, ciz_vaziyet
from modules.rapor_motoru import word_raporu_uret

# ==========================================
# 0. PLAXIS MAKRO ÜRETİCİ FONKSİYON 
# ==========================================
def plaxis_makrosu_uret(df, kuyu_adi="SK-01"):
    script = f'"""\nLique3D Otomatik PLAXIS 2D Entegrasyon Makrosu\nKuyu: {kuyu_adi}\n"""\n'
    script += "from plxscripting.easy import *\n"
    script += "import sys\n\n"
    script += "localhost_port = 10000\n"
    script += "password = '12345'\n\n"
    script += "try:\n"
    script += "    s, g_i = new_server('localhost', localhost_port, password=password)\n"
    script += "except Exception as e:\n"
    script += "    print('Baglanti Hatasi:', e)\n"
    script += "    sys.exit()\n\n"
    script += "s.new()\n"
    script += "bh = g_i.borehole(0.0)\n\n"
    
    onceki_derinlik = 0.0 
    for i, (pandas_index, row) in enumerate(df.iterrows()):
        derinlik = float(row['Derinlik_m'])
        kalinlik = derinlik - onceki_derinlik 
        
        zemin_sinifi = str(row['Zemin_Sinifi'])
        gamma = float(row.get('Gamma_Tasarim', 19.0))
        cu = float(row.get('Cu_Tasarim', 0.0)) if pd.notna(row.get('Cu_Tasarim', 0.0)) else 0.0
        phi = float(row.get('Phi_Acisi', 30.0)) if pd.notna(row.get('Phi_Acisi', 30.0)) else 0.0
        e_mod = float(row.get('E_Modulu', 10000.0))
        
        guvenli_isim = zemin_sinifi.replace("-", "_").replace(" ", "_").replace("/", "_")
        mat_adi = f"Mat_{i+1}_{guvenli_isim}"
        
        if cu > 0:
            script += f"{mat_adi} = g_i.soilmat('Identification', '{zemin_sinifi} ({derinlik}m)', 'SoilModel', 'Mohr-Coulomb', 'DrainageType', 'Undrained (B)', 'gammaUnsat', {gamma:.2f}, 'gammaSat', {gamma + 1.0:.2f}, 'Eref', {e_mod:.0f}, 'nu', 0.35, 'cref', {cu:.2f})\n"
        else:
            c_val = cu if cu > 0 else 1.0
            script += f"{mat_adi} = g_i.soilmat('Identification', '{zemin_sinifi} ({derinlik}m)', 'SoilModel', 'Mohr-Coulomb', 'DrainageType', 'Drained', 'gammaUnsat', {gamma:.2f}, 'gammaSat', {gamma + 1.0:.2f}, 'Eref', {e_mod:.0f}, 'nu', 0.35, 'cref', {c_val:.2f}, 'phi', {phi:.2f})\n"
        
        script += f"g_i.soillayer(bh, {kalinlik:.2f})\n"
        script += f"g_i.set(bh.SoilLayers[{i}].Material, {mat_adi})\n\n"
        onceki_derinlik = derinlik 
        
    script += "print('Lique3D Verileri PLAXIS 2D 2025 Ortamina Basariyla Aktarildi!')\n"
    return script.encode('utf-8')

# ==========================================
# 1. ARAYÜZ VE HAFIZA (SESSION STATE) KURULUMU
# ==========================================
st.set_page_config(page_title="Lique3D | Geotechnical Platform", page_icon="🌍", layout="wide")

if 'aktif_adim' not in st.session_state: st.session_state.aktif_adim = 0
if 'ham_df' not in st.session_state: st.session_state.ham_df = None
if 'sismik' not in st.session_state: 
    st.session_state.sismik = {'pga': 0.300, 'ss': 0.750, 's1': 0.250, 'mw': 7.5, 'dd': 'DD-2 (475 Yıl - Standart Tasarım)'}
if 'iyilestirme' not in st.session_state:
    st.session_state.iyilestirme = {'aktif': False, 'cap': 80, 'grid': 1.5, 'alan': 3000, 'fiyat': 850}
if 'analiz_sonuclari' not in st.session_state: st.session_state.analiz_sonuclari = None

def ileri(): st.session_state.aktif_adim += 1
def geri(): st.session_state.aktif_adim -= 1
def vitrine_don(): st.session_state.aktif_adim = 0; st.session_state.clear()

# --- JANJANLI VİTRİN CSS KODLARI ---
st.markdown("""
    <style>
    .hero-title { font-size: 4.5rem !important; font-weight: 900; color: #7A5CFF; margin-bottom: 0rem; padding-bottom: 0rem; }
    .hero-subtitle { font-size: 1.3rem; color: #E0E6ED; margin-bottom: 2rem; font-family: 'Courier New', Courier, monospace; }
    .feature-box { background-color: #1E2433; padding: 20px; border-radius: 10px; border-left: 5px solid #7A5CFF; height: 100%; }
    </style>
""", unsafe_allow_html=True)


# ==========================================
# 2. YAN MENÜ (SADECE GPS GÖREVİ GÖRÜR)
# ==========================================
with st.sidebar:
    st.markdown("### 🌍 Lique3D İş Akışı")
    
    ilerleme_orani = 0.0 if st.session_state.aktif_adim == 0 else (st.session_state.aktif_adim / 5.0)
    st.progress(ilerleme_orani)
    
    st.markdown(f"{'🏠' if st.session_state.aktif_adim == 0 else '✅'} **0. Ana Sayfa (Vitrin)**")
    st.markdown(f"{'🔵' if st.session_state.aktif_adim == 1 else ('✅' if st.session_state.aktif_adim > 1 else '⏳')} **1. Sondaj Veri Girişi**")
    st.markdown(f"{'🔵' if st.session_state.aktif_adim == 2 else ('✅' if st.session_state.aktif_adim > 2 else '⏳')} **2. Sismik (AFAD) Ayarları**")
    st.markdown(f"{'🔵' if st.session_state.aktif_adim == 3 else ('✅' if st.session_state.aktif_adim > 3 else '⏳')} **3. Geoteknik Analiz & 3B**")
    st.markdown(f"{'🔵' if st.session_state.aktif_adim == 4 else ('✅' if st.session_state.aktif_adim > 4 else '⏳')} **4. Zemin İyileştirme**")
    st.markdown(f"{'🔵' if st.session_state.aktif_adim == 5 else '⏳'} **5. Rapor & PLAXIS Çıktısı**")
    
    st.divider()
    st.caption("Filyos 3D Motoru ile Güçlendirilmiştir.")


# ==========================================
# 3. ANA EKRAN - SİHİRBAZ ADIMLARI
# ==========================================

# ----------------- ADIM 0: VİTRİN / ANA SAYFA -----------------
if st.session_state.aktif_adim == 0:
    st.markdown('<p class="hero-title">Lique3D</p>', unsafe_allow_html=True)
    st.markdown('<p class="hero-subtitle">Yeni Nesil Geoteknik Analiz ve 3B Zemin Modelleme Platformu</p>', unsafe_allow_html=True)
    
    st.write("Sondaj verilerinizi analiz edin, sıvılaşma risklerini haritalayın ve tek tıkla PLAXIS 2D entegrasyonu sağlayın.")
    st.markdown("<br>", unsafe_allow_html=True)
    
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown('<div class="feature-box"><b>🌊 TBDY-2018 Sismik Analiz</b><br><br>AFAD verilerini otomatik okur, PGA ve spektrum eğrilerini çizer. Spektral ivmelere göre sıvılaşma potansiyelini (FS) belirler.</div>', unsafe_allow_html=True)
    with c2:
        st.markdown('<div class="feature-box"><b>🌐 3B Zemin İskeleti</b><br><br>Plotly altyapısıyla sondaj loglarınızı 3 boyutlu uzayda birleştirir, derinliğe bağlı izohips haritaları üretir.</div>', unsafe_allow_html=True)
    with c3:
        st.markdown('<div class="feature-box"><b>🤖 PLAXIS & Word Otomasyonu</b><br><br>Girdiğiniz verileri saniyeler içinde detaylı Word raporuna ve otomatik PLAXIS 2D makrosuna (.py) dönüştürür.</div>', unsafe_allow_html=True)
    
    st.markdown("<br><br>", unsafe_allow_html=True)
    
    satir1, satir2, satir3 = st.columns([1, 2, 1])
    with satir2:
        if st.button("🚀 Lique3D Çalışma İstasyonunu Başlat", type="primary", use_container_width=True):
            st.session_state.aktif_adim = 1
            st.rerun()

# ----------------- ADIM 1: VERİ GİRİŞİ -----------------
elif st.session_state.aktif_adim == 1:
    st.title("Adım 1: Proje ve Veri Girişi 📁")
    st.write("Analize başlamak için sondaj kuyu verilerinizi sisteme tanımlayın.")
    
    veri_giris_modu = st.radio("Veri Giriş Yöntemi Seçiniz:", ["Çoklu Kuyu (CSV / Excel Yükle)", "Hızlı Tek Kuyu (Manuel Tablo)"], horizontal=True)
    
    gecici_df = None
    if "Çoklu Kuyu" in veri_giris_modu:
        yuklenen_dosya = st.file_uploader("Sondaj Verisi (CSV) Yükle", type=['csv'])
        if yuklenen_dosya is not None:
            gecici_df = pd.read_csv(yuklenen_dosya, sep=';')
            st.success(f"{len(gecici_df)} satır veri başarıyla okundu.")
    else:
        c1, c2 = st.columns(2)
        hizli_kuyu_adi = c1.text_input("Sondaj Kuyusu Adı", value="SK-01")
        hizli_yass = c2.number_input("Yeraltı Su Seviyesi - YASS (m)", value=2.0, step=0.5)
        
        sablon_df = pd.DataFrame({"Derinlik_m": [1.5, 3.0, 4.5], "N_arazi": [10, 15, 12], "FC": [15.0, 20.0, 10.0], "PI": [0.0, 0.0, 0.0], "Zemin_Sinifi": ["SM", "SC", "SP"]})
        hizli_veri_df = st.data_editor(sablon_df, num_rows="dynamic", use_container_width=True)
        
        hizli_veri_df['Sondaj_No'] = hizli_kuyu_adi
        hizli_veri_df['GYS_m'] = hizli_yass
        hizli_veri_df['X_Koordinat_m'] = 0.0; hizli_veri_df['Y_Koordinat_m'] = 0.0
        gecici_df = hizli_veri_df

    st.divider()
    col1, col2 = st.columns([1, 5])
    with col1:
        if st.button("⬅️ Vitrine Dön"): vitrine_don(); st.rerun()
    with col2:
        if st.button("Verileri Kaydet ve İleri ➡️", type="primary"):
            if gecici_df is not None and not gecici_df.empty:
                if 'Zemin_Sini' in gecici_df.columns: gecici_df.rename(columns={'Zemin_Sini': 'Zemin_Sinifi'}, inplace=True)
                if 'PI' not in gecici_df.columns: gecici_df['PI'] = 0.0
                if 'FC' not in gecici_df.columns: gecici_df['FC'] = 0.0
                st.session_state.ham_df = gecici_df
                ileri()
                st.rerun()
            else:
                st.error("Lütfen ilerlemeden önce veri girişini tamamlayın.")

# ----------------- ADIM 2: SİSMİK AYARLAR -----------------
elif st.session_state.aktif_adim == 2:
    st.title("Adım 2: Sismik ve AFAD Parametreleri 🌍")
    st.write("Verileriniz güvende. Şimdi projenin maruz kalacağı tasarım depremini belirleyelim.")
    
    afad_dosya = st.file_uploader("AFAD Raporu (PDF/TXT) Yükle (Otomatik Okuma İçin)", type=['pdf', 'txt'])
    
    c1, c2, c3 = st.columns(3)
    pga_input = c1.number_input("PGA (İvme)", value=st.session_state.sismik['pga'], step=0.01)
    ss_input = c2.number_input("Ss (Kısa Periyot)", value=st.session_state.sismik['ss'], step=0.01)
    s1_input = c3.number_input("S1 (1.0sn Periyot)", value=st.session_state.sismik['s1'], step=0.01)
    mw_input = st.slider("Deprem Büyüklüğü (Mw)", 6.0, 8.0, st.session_state.sismik['mw'], 0.1)
    
    st.divider()
    col1, col2, col3 = st.columns([1, 4, 1])
    with col1:
        if st.button("⬅️ Geri Dön"): geri(); st.rerun()
    with col3:
        if st.button("Analizi Başlat ➡️", type="primary"):
            st.session_state.sismik.update({'pga': pga_input, 'ss': ss_input, 's1': s1_input, 'mw': mw_input})
            ileri()
            st.rerun()

# ----------------- ADIM 3: ANALİZ VE 3B MODELLEME -----------------
elif st.session_state.aktif_adim == 3:
    st.title("Adım 3: Geoteknik Analiz ve 3B Modelleme 📊")
    
    if st.session_state.analiz_sonuclari is None:
        with st.spinner("Lique3D Matrisleri Çözülüyor... (Lütfen Bekleyin)"):
            df, kuyu_oturmalari, s = geoteknik_analiz(
                st.session_state.ham_df, st.session_state.sismik['pga'], st.session_state.sismik['ss'], 
                st.session_state.sismik['s1'], st.session_state.sismik['mw'], 0.83, 1.0, 1.0, 0.0, 0.0, 
                False, False, False, 80, 1.5, 3000, 850, True
            )
            st.session_state.analiz_sonuclari = {'df': df, 'kuyu_oturmalari': kuyu_oturmalari, 's': s}
    
    df = st.session_state.analiz_sonuclari['df']
    s = st.session_state.analiz_sonuclari['s']
    kuyu_oturmalari = st.session_state.analiz_sonuclari['kuyu_oturmalari']
    
    tab_deprem, tab_param, tab_3d, tab_2d, tab_vaziyet = st.tabs(["🌊 Deprem Spektrumu", "📋 Statik Tasarım", "🌐 3B Model", "📉 2B Kesit", "🗺️ İzohips Planı"])
    
    with tab_deprem:
        st.success(f"Yerel Zemin Sınıfı: {s.get('zemin_sinifi', 'ZE')} hesaplandı.")
        try:
            fig_spec = ciz_spektrum(s['T_vals'], s['Sae_vals'], s['TA'], s['TB'], "DD-2")
            st.plotly_chart(fig_spec, use_container_width=True)
        except: st.warning("Çizim modülü hazır değil.")
    
    with tab_param:
        st.dataframe(df[['Sondaj_No', 'Derinlik_m', 'Zemin_Sinifi', 'Zemin_Tipi', 'Dr_Yuzde', 'Cu_Tasarim', 'E_Modulu']], use_container_width=True)
        
    with tab_3d:
        ayar_sutunu, bos_sutun = st.columns([1, 3]) 
        
        with ayar_sutunu:
            st.markdown("##### 🎛️ 3B Model Filtreleri")
            hedef_derinlik = st.slider("🔍 Kesit Derinliği (m)", min_value=1.0, max_value=40.0, value=15.0, step=0.5)
            
            st.divider()
            tum_kuyular = list(df['Sondaj_No'].unique())
            secili_3d_kuyular = st.multiselect("🎯 Gösterilecek Sondajlar:", tum_kuyular, default=tum_kuyular)
            
            goster_sondajlar = st.toggle("📍 Sondajları Aç/Kapat", value=True)
            goster_riskli_zon = st.toggle("⚠️ Sadece Sıvılaşabilir Zonları Göster", value=False)
            goster_kritik_oturma = st.toggle("💥 Sadece >10 cm Oturma Göster", value=False)
            
        try:
            fig3d = ciz_3d(
                df=df, 
                hedef_derinlik=hedef_derinlik, 
                goster_sondajlar=goster_sondajlar, 
                secili_kuyular=secili_3d_kuyular, 
                goster_riskli_zon=goster_riskli_zon, 
                goster_kritik_oturma=goster_kritik_oturma
            )
            st.plotly_chart(fig3d, use_container_width=True)
        except Exception as e: 
            st.info(f"3B Model Çizilemedi: {e}")

    with tab_2d:
        tum_kuyular = list(df['Sondaj_No'].unique())
        secili_kuyular = st.multiselect(
            "🔍 Kesit Hattı İçin Kuyuları Seçin:", 
            tum_kuyular, 
            default=tum_kuyular[:3] if len(tum_kuyular)>=3 else tum_kuyular
        )
        if len(secili_kuyular) >= 2:
            try:
                fig2d = ciz_2d(df, secili_kuyular)
                st.plotly_chart(fig2d, use_container_width=True)
            except Exception as e: 
                st.info(f"2B Kesit Çizilemedi: {e}")
        else:
            st.warning("⚠️ 2B kesit (profil) çizebilmek için en az 2 kuyu seçmelisiniz.")
            
    with tab_vaziyet:
        if len(kuyu_oturmalari) >= 3:
            try:
                fig_vaziyet = ciz_vaziyet(kuyu_oturmalari)
                st.plotly_chart(fig_vaziyet, use_container_width=True)
            except: pass
        else: st.info("İzohips için en az 3 kuyu gereklidir.")

    st.divider()
    col1, col2, col3 = st.columns([1, 4, 1.5])
    with col1:
        if st.button("⬅️ Sismik Ayarlara Dön"): 
            st.session_state.analiz_sonuclari = None
            geri()
            st.rerun()
    with col3:
        if st.button("Zemin İyileştirmeye Geç ➡️", type="primary"): 
            ileri()
            st.rerun()

# ----------------- ADIM 4: ZEMİN İYİLEŞTİRME -----------------
elif st.session_state.aktif_adim == 4:
    st.title("Adım 4: Zemin İyileştirme Tasarımı 🏗️")
    st.write("Sıvılaşma veya oturma riskine karşı Jet-Grout veya Taş Kolon ağını tasarlayın.")
    
    iyilestirme_toggle = st.toggle("İyileştirme Simülasyonunu Aktif Et", value=st.session_state.iyilestirme['aktif'])
    
    c1, c2, c3 = st.columns(3)
    cap_input = c1.selectbox("Kolon Çapı (cm)", [60, 80, 100, 120], index=1)
    grid_input = c2.slider("Grid Aralığı (m)", 0.5, 4.0, st.session_state.iyilestirme['grid'])
    alan_input = c3.number_input("İyileştirilecek Alan (m2)", value=st.session_state.iyilestirme['alan'])
    
    if st.button("Tasarımı Test Et ⚙️"):
        st.session_state.iyilestirme.update({'aktif': iyilestirme_toggle, 'cap': cap_input, 'grid': grid_input, 'alan': alan_input})
        with st.spinner("İyileştirilmiş Zemin Çözülüyor..."):
            df, kuyu_oturmalari, s = geoteknik_analiz(
                st.session_state.ham_df, st.session_state.sismik['pga'], st.session_state.sismik['ss'], 
                st.session_state.sismik['s1'], st.session_state.sismik['mw'], 0.83, 1.0, 1.0, 0.0, 0.0, 
                False, False, iyilestirme_toggle, cap_input, grid_input, alan_input, 850, True
            )
            st.session_state.analiz_sonuclari = {'df': df, 'kuyu_oturmalari': kuyu_oturmalari, 's': s}
        
        st.success("İyileştirme Başarılı!")
        m1, m2, m3 = st.columns(3)
        m1.metric("Yeni Maks. Oturma", f"{s.get('max_oturma', 0):.1f} cm")
        m2.metric("Yer Değiştirme Oranı", f"% {s.get('Ar', 0)*100:.1f}")
        m3.metric("Kolon Sayısı", f"{s.get('toplam_kolon_sayisi', 0)} Adet")
    
    st.divider()
    col1, col2, col3 = st.columns([1, 4, 1.5])
    with col1:
        if st.button("⬅️ Analize Dön"): geri(); st.rerun()
    with col3:
        if st.button("Rapor ve Çıktıları Al ➡️", type="primary"): 
            st.session_state.iyilestirme['aktif'] = iyilestirme_toggle
            ileri()
            st.rerun()

# ----------------- ADIM 5: RAPOR VE PLAXIS -----------------
elif st.session_state.aktif_adim == 5:
    st.title("Adım 5: Nihai Rapor ve PLAXIS Çıktısı 📄")
    st.success("Tüm mühendislik hesaplamaları tamamlandı. Çıktılarınızı alabilirsiniz.")
    
    df = st.session_state.analiz_sonuclari['df']
    s = st.session_state.analiz_sonuclari['s']
    
    tab_rapor, tab_plaxis = st.tabs(["📑 Excel & Word Raporu", "🔵 PLAXIS 2D Entegrasyonu"])
    
    with tab_rapor:
        st.dataframe(df[['Sondaj_No', 'Derinlik_m', 'Zemin_Sinifi', 'N_arazi', 'FS', 'Tabaka_Oturmasi_cm']], use_container_width=True)
        csv_cikti = df.to_csv(index=False, sep=';').encode('utf-8-sig') 
        st.download_button("📥 Tabloyu Excel Olarak İndir", data=csv_cikti, file_name='Lique3D_Rapor.csv', mime='text/csv')
        
        try:
            s['PGA'] = st.session_state.sismik['pga']
            word_dosyasi = word_raporu_uret(df, s, st.session_state.sismik['dd'])
            st.download_button(label="📝 Kapsamlı Word Raporunu İndir", data=word_dosyasi, file_name=f"Geoteknik_Rapor.docx", mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        except: st.warning("Word Rapor motoru modülü bulunamadı.")

    with tab_plaxis:
        st.info("Hesaplanan statik zemin parametrelerini PLAXIS 2D ortamına aktaracak Python makrosunu aşağıdan indirebilirsiniz.")
        secili_kuyu_plaxis = st.selectbox("Aktarılacak Kuyuyu Seçin:", df['Sondaj_No'].unique())
        plaxis_icin_df = df[df['Sondaj_No'] == secili_kuyu_plaxis].sort_values('Derinlik_m')
        
        plaxis_dosyasi = plaxis_makrosu_uret(plaxis_icin_df, secili_kuyu_plaxis)
        st.download_button(label="🐍 PLAXIS Makrosunu İndir (.py)", data=plaxis_dosyasi, file_name=f"Lique3D_to_PLAXIS_{secili_kuyu_plaxis}.py", mime="text/x-python")

    st.divider()
    col1, col2 = st.columns([1, 5])
    with col1:
        if st.button("⬅️ Tasarıma Dön"): geri(); st.rerun()
    with col2:
        if st.button("🔄 Yeni Projeye Başla (Sıfırla)", type="primary"): 
            st.session_state.clear()
            st.rerun()
