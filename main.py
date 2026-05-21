import streamlit as st
import pandas as pd
import re
from modules.hesap_motoru import geoteknik_analiz
from modules.cizim_motoru import ciz_spektrum, ciz_3d, ciz_2d, ciz_vaziyet
from modules.rapor_motoru import word_raporu_uret

st.set_page_config(page_title="Lique3D Analiz Sistemi", layout="wide")
st.title("Lique3D: Geoteknik Analiz ve Sismik Iyilestirme Sistemi")
st.markdown("*Kurumsal Geoteknik Karar Destek, AFAD Entegrasyonu ve Statik Tasarim Motoru*")

# 1. YAN MENU ARAYUZU
st.sidebar.header("1. Veri Kaynagi")
yuklenen_dosya = st.sidebar.file_uploader("Sondaj Verisi (CSV)", type=['csv'])

st.sidebar.header("2. Deprem ve Zemin")
afad_dosya = st.sidebar.file_uploader("AFAD Raporu (PDF/TXT)", type=['pdf', 'txt', 'csv'])

afad_verileri = {
    "DD-1 (2475 Yil - Ozel Yapilar)": {"PGA": 0.450, "Ss": 1.100, "S1": 0.350},
    "DD-2 (475 Yil - Standart Tasarim)": {"PGA": 0.300, "Ss": 0.750, "S1": 0.250},
    "DD-3 (72 Yil - Sik Deprem)": {"PGA": 0.200, "Ss": 0.500, "S1": 0.150},
    "DD-4 (43 Yil - Servis Depremi)": {"PGA": 0.100, "Ss": 0.250, "S1": 0.080}
}
secilen_dd = st.sidebar.selectbox("Hedef Deprem Duzeyi", list(afad_verileri.keys()), index=1)

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
        if pga_match: afad_durum = f"BASARILI: {secilen_dd[:4]} verileri okundu."
    except Exception:
        pass
st.sidebar.info(afad_durum)

with st.sidebar.expander("Ileri Sismik ve Laboratuvar Ayarlari", expanded=False):
    pga_val = st.number_input("PGA (Ivme)", value=afad_verileri[secilen_dd]["PGA"], step=0.001, format="%.3f")
    ss_val = st.number_input("Ss (Kisa Periyot)", value=afad_verileri[secilen_dd]["Ss"], step=0.001, format="%.3f")
    s1_val = st.number_input("S1 (1.0sn Periyot)", value=afad_verileri[secilen_dd]["S1"], step=0.001, format="%.3f")
    mw = st.slider("Deprem Buyuklugu (Mw)", 6.0, 8.0, 7.5, 0.1)
    
    ce_val = st.number_input("Enerji Orani (CE)", value=0.83, step=0.01)
    cb_val = st.number_input("Kuyu Capi (CB)", value=1.00, step=0.01)
    cs_val = st.number_input("Numune Alici (CS)", value=1.00, step=0.01)
    
    vs30_val = st.number_input("Olculen Vs30 (m/s)", value=0, step=10)
    cu30_val = st.number_input("Laboratuvar Cu30 (kPa)", value=0, step=10)
    ze_ozel_kosul = st.checkbox("ZE Ozel Kil Kosulu")
    zf_ozel_kosul = st.checkbox("ZF Ozel Saha Kosulu")

st.sidebar.header("3. Zemin Iyilestirme")
iyilestirme_aktif = st.sidebar.toggle("Jet-Grout / Tas Kolon Uygula", value=False)
tasarim_capi = st.sidebar.selectbox("Kolon Capi (cm)", [60, 80, 100, 120], index=1)
tasarim_grid = st.sidebar.slider("Grid Araligi (m)", 0.5, 4.0, 1.5, 0.1)

with st.sidebar.expander("Proje ve Gorsel Ayarlar", expanded=False):
    proje_alani = st.number_input("Iyilestirilecek Alan (m2)", value=3000, step=100)
    birim_fiyat = st.number_input("Birim Imalat Fiyati (TL/m)", value=850, step=50)
    hedef_derinlik = st.slider("3B Harita Derinligi (m)", 1.0, 20.0, 5.0, 0.5)
    kati_filtre_aktif = st.checkbox("TBDY Kil Sartini Koru", value=True)

# 2. SISTEM CALISTIRMA VE GORSELLESTIRME
@st.cache_data
def csv_oku(dosya):
    if dosya is not None:
        return pd.read_csv(dosya, sep=';')
    return None

try:
    ham_df = csv_oku(yuklenen_dosya)
    
    if ham_df is not None and len(ham_df) > 0:
        # Analiz Modulunu Cagir (Tek satirda tum hesaplamalar yapilir)
        df, kuyu_oturmalari, s = geoteknik_analiz(
            ham_df, pga_val, ss_val, s1_val, mw, ce_val, cb_val, cs_val, 
            vs30_val, cu30_val, ze_ozel_kosul, zf_ozel_kosul, iyilestirme_aktif, 
            tasarim_capi, tasarim_grid, proje_alani, birim_fiyat, kati_filtre_aktif
        )

        tab_deprem, tab_param, tab_3d, tab_2d, tab_vaziyet, tab_ai, tab_rapor = st.tabs([
            "Deprem Spektrumu", "Statik Tasarim", "3B Model", "2B Kesit", 
            "Izohips Plani", "Iyilestirme Simulasyonu", "Rapor Ciktisi"
        ])

        with tab_deprem:
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Yerel Zemin Sinifi", s['zemin_sinifi'], s['zemin_nedeni'])
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
            goster_param.columns = ['Kuyu No', 'Derinlik (m)', 'Sinif', 'Davranis', 'Birim Hacim Agirlik (kN/m3)', 'Surtunme Acisi', 'Dr (%)', 'Cu (kPa)', 'E Modulu (kPa)']
            st.dataframe(goster_param.style.format({'Birim Hacim Agirlik (kN/m3)': '{:.1f}', 'Surtunme Acisi': '{:.1f}', 'Dr (%)': '{:.1f}', 'Cu (kPa)': '{:.1f}', 'E Modulu (kPa)': '{:.0f}'}, na_rep="-"), use_container_width=True)

        with tab_3d:
            fig3d = ciz_3d(df, hedef_derinlik)
            st.plotly_chart(fig3d, use_container_width=True)

        with tab_2d:
            tum_kuyular = list(df['Sondaj_No'].unique())
            secili_kuyular = st.multiselect("Kesit Hatti Kuyulari:", tum_kuyular, default=tum_kuyular[:3] if len(tum_kuyular)>=3 else tum_kuyular)
            if len(secili_kuyular) >= 2:
                fig2d = ciz_2d(df, secili_kuyular)
                st.plotly_chart(fig2d, use_container_width=True)

        with tab_vaziyet:
            if len(kuyu_oturmalari) >= 3:
                fig_vaziyet = ciz_vaziyet(kuyu_oturmalari)
                st.plotly_chart(fig_vaziyet, use_container_width=True)
            else:
                st.info("BILGI: Izohips haritasi icin en az 3 sondaj verisi gereklidir.")

        with tab_ai:
            st.markdown(f"**Tasarim Parametreleri:** Cap {tasarim_capi} cm kolon, {tasarim_grid} m grid.")
            if s['max_oturma'] > 4.0: st.error(f"DIKKAT: Maksimum oturma {s['max_oturma']:.1f} cm sinirlari asmaktadir.")
            else: st.success(f"BASARILI: Maksimum oturma {s['max_oturma']:.1f} cm ile guvenli seviyededir.")
                
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Maks. Oturma", f"{s['max_oturma']:.1f} cm")
            c2.metric("Yer Degistirme", f"% {s['Ar']*100:.1f}")
            c3.metric("Kolon Sayisi", f"{s['toplam_kolon_sayisi']} Adet")
            c4.metric("Tahmini Maliyet", f"TL {s['toplam_maliyet']:,.0f}")

        with tab_rapor:
            st.markdown("## Geoteknik Analiz Ciktisi")
            gosterilecek_df = df[['Sondaj_No', 'Derinlik_m', 'Zemin_Sinifi', 'N_arazi', 'CR', 'N60', 'FS', 'Tabaka_Oturmasi_cm']].copy()
            gosterilecek_df.columns = ['Kuyu No', 'Derinlik (m)', 'Zemin Turu', 'Arazi N', 'Tij(CR)', 'N60', 'FS', 'Oturma (cm)']
            st.dataframe(gosterilecek_df.style.format({'Tij(CR)': '{:.2f}', 'N60': '{:.1f}', 'FS': '{:.2f}', 'Oturma (cm)': '{:.2f}'}), use_container_width=True)
            csv_cikti = gosterilecek_df.to_csv(index=False, sep=';').encode('utf-8-sig') 
            st.download_button("Excel Formatinda Indir", data=csv_cikti, file_name='Lique3D_Rapor.csv', mime='text/csv')
            # --- YENİ EKLENEN: WORD RAPORU BUTONU ---
            st.divider()
            st.markdown("### 📝 Yönetici Özeti ve Statik Raporu")
            st.info("Hesaplanan sismik tehlike parametrelerini ve Yüksel Proje standartlarındaki geoteknik tasarım tablolarını Word formatında indirin.")
            
            s['PGA'] = pga_val # Rapor motoru için PGA değerini sözlüğe ekledik
            word_dosyasi = word_raporu_uret(df, s, secilen_dd)
            
            st.download_button(
                label="Word Raporunu İndir (.docx)",
                data=word_dosyasi,
                file_name=f"Geoteknik_Rapor_{secilen_dd[:4]}.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            )
            

    else:
        st.info("Sistemi calistirmak icin sol menuden CSV formati yukleyiniz.")
except Exception as e:
    st.error(f"Sistem Hatasi Olustu: {e}")