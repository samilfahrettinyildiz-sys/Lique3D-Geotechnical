import streamlit as st
import pandas as pd
import re
from modules.hesap_motoru import geoteknik_analiz
from modules.cizim_motoru import ciz_spektrum, ciz_3d, ciz_2d, ciz_vaziyet
from modules.rapor_motoru import word_raporu_uret

# ==========================================
# 0. PLAXIS MAKRO ÜRETİCİ FONKSİYON (DÜZELTİLMİŞ)
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

    script += "# --- ZEMIN PARAMETRELERI VE TABAKALAR ---\n"
    
    for index, row in df.iterrows():
        derinlik = row['Derinlik_m']
        zemin_sinifi = str(row['Zemin_Sinifi'])
        gamma = row['Gamma_Tasarim']
        cu = row['Cu_Tasarim'] if pd.notna(row['Cu_Tasarim']) else 0.0
        phi = row['Phi_Acisi'] if pd.notna(row['Phi_Acisi']) else 0.0
        e_mod = row['E_Modulu']
        
        drainage = 3 if cu > 0 else 1
        
        # Python değişken isminde hata vermemesi için temizlik (Tire, boşluk ve taksimleri alt çizgiye çeviriyoruz)
        guvenli_isim = zemin_sinifi.replace("-", "_").replace(" ", "_").replace("/", "_")
        mat_adi = f"Mat_{index+1}_{guvenli_isim}"
        
        script += f"{mat_adi} = g_i.soilmat('Identification', '{zemin_sinifi} ({derinlik}m)', "
        script += f"'SoilModel', 2, 'DrainageType', {drainage}, "
        script += f"'gammaUnsat', {gamma}, 'gammaSat', {gamma + 1.0}, "
        script += f"'Eref', {e_mod}, 'nu', 0.35, "
        script += f"'cref', {cu if cu > 0 else 1.0}, 'phi', {phi})\n"
        
        script += f"g_i.soillayer(bh)\n"
        script += f"g_i.set(bh.SoilLayers[{index}].Bottom, -{derinlik})\n"
        script += f"g_i.setmaterial(bh.SoilLayers[{index}], {mat_adi})\n\n"
        
    script += "print('Lique3D Verileri PLAXIS 2D Ortamina Basariyla Aktarildi!')\n"
    return script.encode('utf-8')


st.set_page_config(page_title="Lique3D Analiz Sistemi", layout="wide")
st.title("Lique3D: Geoteknik Analiz ve Sismik İyileştirme Sistemi")
st.markdown("*Kurumsal Geoteknik Karar Destek, AFAD Entegrasyonu ve Statik Tasarım Motoru*")

# --- KÖPRÜ DEĞİŞKENLERİ ---
ham_df = None

# ==========================================
# 1. YAN MENÜ (ORTAK AYARLAR)
# ==========================================
st.sidebar.header("1. Veri Kaynağı ve Yöntem")
veri_giris_modu = st.sidebar.radio(
    "Veri Giriş Yöntemi Seçiniz:", 
    ["📁 Çoklu Kuyu (CSV / Excel)", "📝 Hızlı Tek Kuyu (Manuel)"],
    index=0
)

st.sidebar.header("2. Deprem ve Zemin (AFAD)")
afad_dosya = st.sidebar.file_uploader("AFAD Raporu (PDF/TXT)", type=['pdf', 'txt', 'csv'])

afad_verileri = {
    "DD-1 (2475 Yıl - Özel Yapılar)": {"PGA": 0.450, "Ss": 1.100, "S1": 0.350},
    "DD-2 (475 Yıl - Standart Tasarım)": {"PGA": 0.300, "Ss": 0.750, "S1": 0.250},
    "DD-3 (72 Yıl - Sık Deprem)": {"PGA": 0.200, "Ss": 0.500, "S1": 0.150},
    "DD-4 (43 Yıl - Servis Depremi)": {"PGA": 0.100, "Ss": 0.250, "S1": 0.080}
}
secilen_dd = st.sidebar.selectbox("Hedef Deprem Düzeyi", list(afad_verileri.keys()), index=1)

afad_durum = "Manuel Veri Bekleniyor."
if afad_dosya is not None:
    icerik = ""
    if afad_dosya.name.endswith('.pdf'):
        try:
            import PyPDF2
            pdf_okuyucu = PyPDF2.PdfReader(afad_dosya)
            for sayfa in pdf_okuyucu.pages:
                icerik += sayfa.extract_text() + "\n"
        except ImportError:
            pass
    else:
        icerik = afad_dosya.getvalue().decode("utf-8")
    
    try:
        pga_match = re.search(secilen_dd[:4] + r'.*?([0-9]+[.,][0-9]+)', icerik.upper()) 
        if pga_match: afad_durum = f"BAŞARILI: {secilen_dd[:4]} verileri okundu."
    except Exception:
        pass
st.sidebar.info(afad_durum)

with st.sidebar.expander("İleri Sismik ve Laboratuvar Ayarları", expanded=False):
    pga_val = st.number_input("PGA (İvme)", value=afad_verileri[secilen_dd]["PGA"], step=0.001, format="%.3f")
    ss_val = st.number_input("Ss (Kısa Periyot)", value=afad_verileri[secilen_dd]["Ss"], step=0.001, format="%.3f")
    s1_val = st.number_input("S1 (1.0sn Periyot)", value=afad_verileri[secilen_dd]["S1"], step=0.001, format="%.3f")
    mw = st.slider("Deprem Büyüklüğü (Mw)", 6.0, 8.0, 7.5, 0.1)
    
    ce_val = st.number_input("Enerji Oranı (CE)", value=0.83, step=0.01)
    cb_val = st.number_input("Kuyu Çapı (CB)", value=1.00, step=0.01)
    cs_val = st.number_input("Numune Alıcı (CS)", value=1.00, step=0.01)
    
    vs30_val = st.number_input("Ölçülen Vs30 (m/s)", value=0, step=10)
    cu30_val = st.number_input("Laboratuvar Cu30 (kPa)", value=0, step=10)
    ze_ozel_kosul = st.checkbox("ZE Özel Kil Koşulu")
    zf_ozel_kosul = st.checkbox("ZF Özel Saha Koşulu")

st.sidebar.header("3. Zemin İyileştirme")
iyilestirme_aktif = st.sidebar.toggle("Jet-Grout / Taş Kolon Uygula", value=False)
tasarim_capi = st.sidebar.selectbox("Kolon Çapı (cm)", [60, 80, 100, 120], index=1)
tasarim_grid = st.sidebar.slider("Grid Aralığı (m)", 0.5, 4.0, 1.5, 0.1)

with st.sidebar.expander("Proje ve Görsel Ayarlar", expanded=False):
    proje_alani = st.number_input("İyileştirilecek Alan (m2)", value=3000, step=100)
    birim_fiyat = st.number_input("Birim İmalat Fiyatı (TL/m)", value=850, step=50)
    hedef_derinlik = st.slider("3B Harita Derinliği (m)", 1.0, 20.0, 5.0, 0.5)
    kati_filtre_aktif = st.checkbox("TBDY Kil Şartını Koru", value=True)

# ==========================================
# 2. ANA EKRAN (VERİ GİRİŞ ALANI)
# ==========================================
@st.cache_data
def csv_oku(dosya):
    if dosya is not None:
        return pd.read_csv(dosya, sep=';')
    return None

if veri_giris_modu == "📁 Çoklu Kuyu (CSV / Excel)":
    st.info("👈 Sol menüden deprem ayarlarınızı yapın ve aşağıdan CSV dosyanızı yükleyin.")
    yuklenen_dosya = st.file_uploader("Sondaj Verisi (CSV) Yükle", type=['csv'])
    if yuklenen_dosya is not None:
        ham_df = csv_oku(yuklenen_dosya)

else:
    st.markdown("### 📝 Hızlı Tek Kuyu Veri Girişi")
    c1, c2 = st.columns(2)
    hizli_kuyu_adi = c1.text_input("Sondaj Kuyusu Adı", value="SK-01")
    hizli_yass = c2.number_input("Yeraltı Su Seviyesi - YASS (m)", value=2.0, step=0.5)
    
    st.markdown("#### 📊 Tabaka Verileri")
    st.caption("💡 Yeni tabaka eklemek için tablonun en altındaki satıra tıklayın. İstediğiniz kadar derinlik girebilirsiniz.")
    
    sablon_df = pd.DataFrame({
        "Derinlik_m": [1.5, 3.0, 4.5],
        "N_arazi": [10, 15, 12],
        "FC": [15.0, 20.0, 10.0],
        "PI": [0.0, 0.0, 0.0],
        "Zemin_Sinifi": ["SM", "SC", "SP"]
    })
    
    hizli_veri_df = st.data_editor(sablon_df, num_rows="dynamic", use_container_width=True, hide_index=True)
    
    if st.button("🚀 Verileri Analiz Et", use_container_width=True):
        gecici_df = hizli_veri_df.copy()
        gecici_df['Sondaj_No'] = hizli_kuyu_adi
        gecici_df['GYS_m'] = hizli_yass
        gecici_df['X_Koordinat_m'] = 0.0
        gecici_df['Y_Koordinat_m'] = 0.0
        gecici_df['Enlem'] = 0.0 
        gecici_df['Boylam'] = 0.0
        ham_df = gecici_df

# ==========================================
# 3. SİSTEM ÇALIŞTIRMA VE GÖRSELLEŞTİRME
# ==========================================
try:
    if ham_df is not None and len(ham_df) > 0:
        st.divider()
        
        df, kuyu_oturmalari, s = geoteknik_analiz(
            ham_df, pga_val, ss_val, s1_val, mw, ce_val, cb_val, cs_val, 
            vs30_val, cu30_val, ze_ozel_kosul, zf_ozel_kosul, iyilestirme_aktif, 
            tasarim_capi, tasarim_grid, proje_alani, birim_fiyat, kati_filtre_aktif
        )

        tab_deprem, tab_param, tab_3d, tab_2d, tab_vaziyet, tab_ai, tab_rapor, tab_plaxis = st.tabs([
            "Deprem Spektrumu", "Statik Tasarım", "3B Model", "2B Kesit", 
            "İzohips Planı", "İyileştirme Simulasyonu", "Rapor Çıktısı", "PLAXIS Entegrasyonu"
        ])

        with tab_deprem:
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Yerel Zemin Sınıfı", s['zemin_sinifi'], s['zemin_nedeni'])
            c2.metric("PGA", f"{pga_val:.3f} g")
            c3.metric("SDS", f"{s['SDS']:.3f} g", f"Fs: {s['Fs']:.2f}")
            c4.metric("SD1", f"{s['SD1']:.3f} g", f"F1: {s['F1']:.2f}")
            
            with st.expander("Ampirik Tahmin Bilgileri (Imai 1976 & Stroud 1974)", expanded=False):
                t1, t2 = st.columns(2)
                t1.metric("Tahmini Ortalama Vs30", f"{s['tahmini_vs30_ort']:.0f} m/s")
                t2.metric("Tahmini Ortalama Cu30", f"{s['tahmini_cu30_ort']:.0f} kPa")

            fig_spec = ciz_spektrum(s['T_vals'], s['Sae_vals'], s['TA'], s['TB'], secilen_dd[:4])
            st.plotly_chart(fig_spec, use_container_width=True)

        with tab_param:
            goster_param = df[['Sondaj_No', 'Derinlik_m', 'Zemin_Sinifi', 'Zemin_Tipi', 'Gamma_Tasarim', 'Phi_Acisi', 'Dr_Yuzde', 'Cu_Tasarim', 'E_Modulu']].copy()
            goster_param.columns = ['Kuyu No', 'Derinlik (m)', 'Sınıf', 'Davranış', 'Birim Hacim Ağırlık (kN/m3)', 'Sürtünme Açısı', 'Dr (%)', 'Cu (kPa)', 'E Modülü (kPa)']
            st.dataframe(goster_param.style.format({'Birim Hacim Ağırlık (kN/m3)': '{:.1f}', 'Sürtünme Açısı': '{:.1f}', 'Dr (%)': '{:.1f}', 'Cu (kPa)': '{:.1f}', 'E Modülü (kPa)': '{:.0f}'}, na_rep="-"), use_container_width=True)

        with tab_3d:
            fig3d = ciz_3d(df, hedef_derinlik)
            st.plotly_chart(fig3d, use_container_width=True)

        with tab_2d:
            tum_kuyular = list(df['Sondaj_No'].unique())
            secili_kuyular = st.multiselect("Kesit Hattı Kuyuları:", tum_kuyular, default=tum_kuyular[:3] if len(tum_kuyular)>=3 else tum_kuyular)
            if len(secili_kuyular) >= 2:
                fig2d = ciz_2d(df, secili_kuyular)
                st.plotly_chart(fig2d, use_container_width=True)

        with tab_vaziyet:
            if len(kuyu_oturmalari) >= 3:
                fig_vaziyet = ciz_vaziyet(kuyu_oturmalari)
                st.plotly_chart(fig_vaziyet, use_container_width=True)
            else:
                st.info("BİLGİ: İzohips haritası için en az 3 sondaj verisi gereklidir.")

        with tab_ai:
            st.markdown(f"**Tasarım Parametreleri:** Çap {tasarim_capi} cm kolon, {tasarim_grid} m grid.")
            if s['max_oturma'] > 4.0: st.error(f"DİKKAT: Maksimum oturma {s['max_oturma']:.1f} cm sınırları aşmaktadır.")
            else: st.success(f"BAŞARILI: Maksimum oturma {s['max_oturma']:.1f} cm ile güvenli seviyededir.")
                
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Maks. Oturma", f"{s['max_oturma']:.1f} cm")
            c2.metric("Yer Değiştirme", f"% {s['Ar']*100:.1f}")
            c3.metric("Kolon Sayısı", f"{s['toplam_kolon_sayisi']} Adet")
            c4.metric("Tahmini Maliyet", f"TL {s['toplam_maliyet']:,.0f}")

        with tab_rapor:
            st.markdown("## Geoteknik Analiz Çıktısı")
            gosterilecek_df = df[['Sondaj_No', 'Derinlik_m', 'Zemin_Sinifi', 'N_arazi', 'CR', 'N60', 'FS', 'Tabaka_Oturmasi_cm']].copy()
            gosterilecek_df.columns = ['Kuyu No', 'Derinlik (m)', 'Zemin Türü', 'Arazi N', 'Tij(CR)', 'N60', 'FS', 'Oturma (cm)']
            st.dataframe(gosterilecek_df.style.format({'Tij(CR)': '{:.2f}', 'N60': '{:.1f}', 'FS': '{:.2f}', 'Oturma (cm)': '{:.2f}'}), use_container_width=True)
            
            csv_cikti = gosterilecek_df.to_csv(index=False, sep=';').encode('utf-8-sig') 
            st.download_button("Excel Formatında İndir", data=csv_cikti, file_name='Lique3D_Rapor.csv', mime='text/csv')
            
            st.divider()
            st.markdown("### 📝 Yönetici Özeti ve Statik Raporu")
            s['PGA'] = pga_val 
            word_dosyasi = word_raporu_uret(df, s, secilen_dd)
            
            st.download_button(
                label="Word Raporunu İndir (.docx)",
                data=word_dosyasi,
                file_name=f"Geoteknik_Rapor_{secilen_dd[:4]}.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            )

        with tab_plaxis:
            st.markdown("## 🔵 PLAXIS 2D Otomatik Model Aktarımı")
            st.info("Bu modül, Lique3D üzerinde analiz ettiğiniz sondaj profilini ve geoteknik parametreleri tek tıkla PLAXIS 2D'ye aktarmanız için bir Python makrosu (.py) üretir.")
            
            st.markdown("""
            **Kullanım Adımları:**
            1. Aşağıdaki butondan makro dosyasını indirin.
            2. PLAXIS 2D programını açın ve *Expert -> Configure remote scripting server* kısmından portu **10000**, şifreyi **12345** yapıp başlatın.
            3. İndirdiğiniz Python dosyasını çalıştırın. Tüm model saniyeler içinde çizilecektir!
            """)
            
            secili_kuyu_plaxis = st.selectbox("Aktarılacak Kuyuyu Seçin:", df['Sondaj_No'].unique())
            plaxis_icin_df = df[df['Sondaj_No'] == secili_kuyu_plaxis].sort_values('Derinlik_m')
            
            plaxis_dosyasi = plaxis_makrosu_uret(plaxis_icin_df, secili_kuyu_plaxis)
            
            st.download_button(
                label="🐍 PLAXIS Makrosunu İndir (.py)",
                data=plaxis_dosyasi,
                file_name=f"Lique3D_to_PLAXIS_{secili_kuyu_plaxis}.py",
                mime="text/x-python"
            )

except Exception as e:
    st.error(f"Sistem Hatası Oluştu: {e}")
