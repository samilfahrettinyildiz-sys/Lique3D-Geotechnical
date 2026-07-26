import pandas as pd
import numpy as np

def geoteknik_analiz(df, SDS, mw, ce_val, cb_val, cs_val, 
                     tasarim_capi, tasarim_grid, iyilestirme_aktif, 
                     proje_alani, birim_fiyat, kati_filtre_aktif):
    
    # 1. KOORDİNAT DÖNÜŞÜMÜ
    min_y, min_x = df['Enlem'].min(), df['Boylam'].min()
    if abs(min_y) > 90 or abs(min_x) > 180:
        df['Y_Koordinat_m'], df['X_Koordinat_m'] = df['Enlem'] - min_y, df['Boylam'] - min_x
    else:
        mean_lat = df['Enlem'].mean()
        df['Y_Koordinat_m'] = (df['Enlem'] - min_y) * 111320.0
        df['X_Koordinat_m'] = (df['Boylam'] - min_x) * (111320.0 * np.cos(np.radians(mean_lat)))

    # Zemin Tipi Belirleme (Kohezyonlu / Kohezyonsuz ayrımı için)
    # Excel'deki mantığa göre Zemin_Sinifi sütununda C veya M harfi varsa Kohezyonlu kabul edilir.
    df['Zemin_Tipi'] = np.where(df['Zemin_Sinifi'].str.contains('C|M', case=False, na=False), 'Kohezyonlu', 'Kohezyonsuz')

    dfs = []
    for sondaj in df['Sondaj_No'].unique():
        kuyu = df[df['Sondaj_No'] == sondaj].sort_values('Derinlik_m').copy()
        
        # Tabaka Kalınlığı (h_i)
        kuyu['h_i'] = kuyu['Derinlik_m'].diff().fillna(kuyu['Derinlik_m'].iloc[0])
        
        # 2. GERİLME (STRESS) HESAPLARI (Excel Mantığı)
        # Kümülatif toplam ile tabaka tabaka ilerleme
        kuyu['Sigma_v'] = np.where(
            kuyu['Derinlik_m'] <= kuyu['GYS_m'],
            kuyu['Derinlik_m'] * kuyu['Gamma_kuru'], 
            (kuyu['GYS_m'] * kuyu['Gamma_kuru']) + ((kuyu['Derinlik_m'] - kuyu['GYS_m']) * kuyu['Gamma_doygun'])
        )
        
        # Boşluk Suyu Basıncı (u) ve Efektif Gerilme (Sigma_ve)
        kuyu['u'] = np.where(kuyu['Derinlik_m'] > kuyu['GYS_m'], (kuyu['Derinlik_m'] - kuyu['GYS_m']) * 9.81, 0.0)
        kuyu['Sigma_ve'] = (kuyu['Sigma_v'] - kuyu['u']).replace(0, 0.001)
        
        dfs.append(kuyu)
        
    df = pd.concat(dfs, ignore_index=True)

    # 3. DİLATANS DÜZELTMESİ (Terzaghi-Peck)
    # Kohezyonsuz, YASS altında ve N >= 15 olan zeminler için
    dilatans_sarti = (df['Zemin_Tipi'] == 'Kohezyonsuz') & (df['Derinlik_m'] >= df['GYS_m']) & (df['N_arazi'] >= 15)
    df['N_prime'] = np.where(dilatans_sarti, 15.0 + 0.5 * (df['N_arazi'] - 15.0), df['N_arazi'])

    # 4. ENERJİ VE ÇUBUK BOYU DÜZELTMELERİ (CR)
    def calc_cr(z):
        if z < 3.0: return 0.75
        elif z < 4.0: return 0.80
        elif z < 6.0: return 0.85
        elif z < 10.0: return 0.95
        else: return 1.00
        
    df['CR'] = df['Derinlik_m'].apply(calc_cr)
    df['N60'] = df['N_prime'] * ce_val * cb_val * cs_val * df['CR']
    df['N60'] = df['N60'].replace(0, 0.1)

    # 5. SIVILAŞMA DÜZELTMELERİ (Youd et al. 2001 & Excel Mantığı)
    
    # CN (Örtü Yükü) Düzeltmesi (Sadece Kohezyonsuz Zeminlerde)
    df['CN'] = np.minimum(1.5, (95.76 / df['Sigma_ve'])**0.5)
    df['N1_60'] = np.where(df['Zemin_Tipi'] == 'Kohezyonsuz', df['N60'] * df['CN'], df['N60'])

    # İnce Dane Düzeltmesi (Alfa ve Beta Katsayıları)
    df['alpha'] = np.where(
        df['FC'] >= 35.0, 5.0,
        np.where(df['FC'] > 5.0, np.exp(1.76 - (190.0 / (df['FC']**2 + 1e-9))), 0.0)
    )
    
    df['beta'] = np.where(
        df['FC'] >= 35.0, 1.2,
        np.where(df['FC'] > 5.0, 0.99 + (df['FC']**1.5) / 1000.0, 1.0)
    )
    
    # Nihai Düzeltilmiş N Değeri
    df['N1_60f'] = df['alpha'] + (df['beta'] * df['N1_60'])

    # 6. SIVILAŞMA DİRENCİ (CRR) VE SİSMİK YÜK (CSR / Tau)
    
    # CRR_M7.5 Hesabı (Asimptot Sınırı: N değeri maksimum 29.99 alınır)
    N_f = np.clip(df['N1_60f'], 0.1, 29.99)
    df['CRR_75'] = (1.0 / (34.0 - N_f)) + (N_f / 135.0) + (50.0 / (10.0 * N_f + 45.0)**2) - (1.0 / 200.0)

    # Deprem Büyüklüğü Katsayısı (CM / MSF) - Idriss (1999)
    df['CM'] = (10**2.24) / (mw**2.56)

    # Derinlik İndirgeme Faktörü (rd) - Liao & Whitman (1986)
    z = df['Derinlik_m']
    df['rd'] = np.where(
        z <= 9.15, 1.0 - 0.00765 * z,
        np.where(
            z <= 23.0, 1.174 - 0.0267 * z,
            np.where(
                z <= 30.0, 0.744 - 0.008 * z,
                0.5
            )
        )
    )

    # Gerilmelerin (Tau) Hesaplanması
    df['tau_r'] = df['CRR_75'] * df['CM'] * df['Sigma_ve']
    
    # TBDY-2018 Maksimum Yer İvmesi (PGA) Mantığı
    pga_hesaplanan = 0.4 * SDS
    
    # İyileştirme Çarpanı (KG)
    Ar = min(0.60, (np.pi * (tasarim_capi / 200.0)**2) / (tasarim_grid**2)) if iyilestirme_aktif else 0.0
    KG = 1.0 / (Ar * 15.0 + 1.0 - Ar) 
    
    df['tau_eq'] = 0.65 * df['Sigma_v'] * pga_hesaplanan * df['rd'] * KG

    # 7. GÜVENLİK KATSAYISI VE OTURMA
    df['FS'] = df['tau_r'] / df['tau_eq'].replace(0, 0.001)

    # Güvenli Bölgelerin Filtrelenmesi (Killer ve YASS üstü)
    kil_sarti = (df['PI'] > 12) | (df['Zemin_Tipi'] == 'Kohezyonlu') if kati_filtre_aktif else pd.Series(False, index=df.index) 
    df.loc[kil_sarti | (df['Derinlik_m'] <= df['GYS_m']) | (df['Derinlik_m'] > 20.0), 'FS'] = 2.0
    
    # FS değerlerini 0.0 ile 2.0 arasında sınırlandırma
    df['FS'] = np.clip(df['FS'], 0.0, 2.0)
    
    # Sınıflandırma
    df['Sivilasma_Durumu'] = np.where(df['FS'] <= 1.0, 'Liquefiable', 'Safe')
    df['Renk'] = df['FS'].apply(lambda fs: 'red' if fs <= 1.0 else ('orange' if fs < 1.1 else 'green'))

    # Oturma Hesabı (Ishihara & Yoshimine) - Gerçek tabaka kalınlığı (h_i) baz alınarak
    sivilasma_mask = (df['FS'] < 1.10) & (df['N1_60f'] < 30) & (df['Derinlik_m'] <= 20.0)
    ev_perc = (1.5 * np.exp(-0.025 * df['N1_60f']) / np.maximum(df['FS'], 0.4)) / 100.0
    df['Tabaka_Oturmasi_cm'] = np.where(sivilasma_mask, ev_perc * (df['h_i'] * 100.0), 0.0) 
    
    iyilestirme_derinligi = df[sivilasma_mask]['Derinlik_m'].max() if sivilasma_mask.any() else 0.0

    # 8. SONUÇLAR VE METRAJ RAPORU
    kuyu_oturmalari = df.groupby('Sondaj_No')['Tabaka_Oturmasi_cm'].sum().reset_index().rename(columns={'Tabaka_Oturmasi_cm': 'Toplam_Oturma_cm'})
    kuyu_oturmalari = pd.merge(kuyu_oturmalari, df.groupby('Sondaj_No')[['X_Koordinat_m', 'Y_Koordinat_m']].first().reset_index(), on='Sondaj_No')

    max_oturma = kuyu_oturmalari['Toplam_Oturma_cm'].max() if not kuyu_oturmalari.empty else 0
    toplam_kolon_sayisi = int(proje_alani / (tasarim_grid**2)) if iyilestirme_aktif and iyilestirme_derinligi > 0 else 0
    toplam_metraj = toplam_kolon_sayisi * iyilestirme_derinligi
    toplam_maliyet = toplam_metraj * birim_fiyat

    sonuclar = {
        'max_oturma': max_oturma,
        'iyilestirme_derinligi': iyilestirme_derinligi,
        'Ar': Ar,
        'toplam_kolon_sayisi': toplam_kolon_sayisi,
        'toplam_metraj': toplam_metraj,
        'toplam_maliyet': toplam_maliyet
    }

    return df, kuyu_oturmalari, sonuclar
