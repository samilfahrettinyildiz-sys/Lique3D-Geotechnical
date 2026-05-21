import pandas as pd
import numpy as np

def geoteknik_analiz(df, pga_val, ss_val, s1_val, mw, ce_val, cb_val, cs_val, 
                     vs30_val, cu30_val, ze_ozel_kosul, zf_ozel_kosul, 
                     iyilestirme_aktif, tasarim_capi, tasarim_grid, 
                     proje_alani, birim_fiyat, kati_filtre_aktif):
    
    # Koordinat Donusumu
    min_y, min_x = df['Enlem'].min(), df['Boylam'].min()
    if abs(min_y) > 90 or abs(min_x) > 180:
        df['Y_Koordinat_m'], df['X_Koordinat_m'] = df['Enlem'] - min_y, df['Boylam'] - min_x
    else:
        mean_lat = df['Enlem'].mean()
        df['Y_Koordinat_m'] = (df['Enlem'] - min_y) * 111320.0
        df['X_Koordinat_m'] = (df['Boylam'] - min_x) * (111320.0 * np.cos(np.radians(mean_lat)))

    # N60 ve Ampirik Tahminler
    def calc_cr(z):
        if z < 3.0: return 0.75
        elif z < 4.0: return 0.80
        elif z < 6.0: return 0.85
        elif z < 10.0: return 0.95
        else: return 1.00
        
    df['CR'] = df['Derinlik_m'].apply(calc_cr)
    df['N60'] = df['N_arazi'] * ce_val * cb_val * cs_val * df['CR']
    df['N60'] = df['N60'].replace(0, 0.1)
    df['Vs_tahmini'] = 89.8 * (df['N60'] ** 0.34)

    def calc_cu(row):
        pi = row.get('PI', 0) if not pd.isna(row.get('PI', 0)) else 0
        if pi < 20: return 6.5 * row['N60']
        elif pi <= 30: return 4.5 * row['N60']
        else: return 4.2 * row['N60']
    df['Cu_tahmini'] = df.apply(calc_cu, axis=1)

    gamma, pa = 19.0, 100.0 
    df['Sigma_v'] = df['Derinlik_m'] * gamma
    df['u'] = np.where(df['Derinlik_m'] > df['GYS_m'], (df['Derinlik_m'] - df['GYS_m']) * 9.81, 0)
    df['Sigma_ve'] = (df['Sigma_v'] - df['u']).replace(0, 0.001)

    # Statik Tasarim Parametreleri
    def calc_design_params(row):
        z_cls = str(row['Zemin_Sinifi']).upper()
        is_clay = any(c in z_cls for c in ['C', 'M'])
        n60 = row['N60']
        sig_ve = row['Sigma_ve']
        gamma_t = 17.0 if n60 < 5 else (18.0 if n60 <= 15 else (19.0 if n60 <= 30 else 20.0))
        
        if is_clay:
            cu = row['Cu_tahmini']
            eu = 300.0 * cu
            return pd.Series(['Kohezyonlu', None, None, cu, eu, gamma_t])
        else:
            val = n60 / (12.2 + 20.3 * (sig_ve / pa))
            phi_deg = np.degrees(np.arctan(val ** 0.34))
            dr_pct = max(0, min(100, ((phi_deg - 28.0) / 15.0) * 100))
            es = 500.0 * (n60 + 15)
            return pd.Series(['Kohezyonsuz', phi_deg, dr_pct, None, es, gamma_t])

    df[['Zemin_Tipi', 'Phi_Acisi', 'Dr_Yuzde', 'Cu_Tasarim', 'E_Modulu', 'Gamma_Tasarim']] = df.apply(calc_design_params, axis=1)

    # Sivilasma Hesaplari
    rd = np.exp(-1.012 - 1.126 * np.sin(df['Derinlik_m']/11.73 + 5.133) + (0.106 + 0.118 * np.sin(df['Derinlik_m']/11.28 + 5.142)) * mw)
    df['CN'] = np.minimum(2.0, (pa / df['Sigma_ve'])**0.5)
    df['N160cs'] = (df['N60'] * df['CN']) + np.exp(1.63 + 9.7/(df['FC']+0.1) - (15.7/(df['FC']+0.1))**2)
    df['CRR'] = np.exp((df['N160cs']/14.1) + (df['N160cs']/126)**2 - (df['N160cs']/23.6)**3 + (df['N160cs']/23.6)**4 - 2.8) * (6.9 * np.exp(-mw/4) - 0.058)

    # TBDY 2018 Harmonik Ortalama
    n60_30_list, vs30_list, cu30_list = [], [], []
    for sondaj in df['Sondaj_No'].unique():
        kuyu_df = df[df['Sondaj_No'] == sondaj].sort_values('Derinlik_m').copy()
        kuyu_df['h_i'] = kuyu_df['Derinlik_m'].diff().fillna(kuyu_df['Derinlik_m'].iloc[0])
        
        kuyu_df_30 = kuyu_df[kuyu_df['Derinlik_m'] <= 30.0].copy()
        if kuyu_df_30.empty: continue
        
        max_d = kuyu_df_30['Derinlik_m'].max()
        last_n60 = kuyu_df_30['N60'].iloc[-1]
        last_vs = kuyu_df_30['Vs_tahmini'].iloc[-1]
        last_cu = kuyu_df_30['Cu_tahmini'].iloc[-1]
        
        sum_h_over_n = (kuyu_df_30['h_i'] / kuyu_df_30['N60']).sum()
        sum_h_over_vs = (kuyu_df_30['h_i'] / kuyu_df_30['Vs_tahmini']).sum()
        sum_h_over_cu = (kuyu_df_30['h_i'] / kuyu_df_30['Cu_tahmini']).sum()
        
        if max_d < 30.0:
            sum_h_over_n += ((30.0 - max_d) / last_n60)
            sum_h_over_vs += ((30.0 - max_d) / last_vs)
            sum_h_over_cu += ((30.0 - max_d) / last_cu)
            
        n60_30_list.append(30.0 / sum_h_over_n)
        vs30_list.append(30.0 / sum_h_over_vs)
        cu30_list.append(30.0 / sum_h_over_cu)
        
    n_ortalama = np.mean(n60_30_list) if n60_30_list else 15.0
    tahmini_vs30_ort = np.mean(vs30_list) if vs30_list else 0.0
    tahmini_cu30_ort = np.mean(cu30_list) if cu30_list else 0.0

    # Zemin Sinifi Karar Agaci
    if zf_ozel_kosul: zemin_sinifi, zemin_nedeni = 'ZF', "Ozel Kosul (ZF)"
    elif vs30_val > 0:
        if vs30_val >= 760: zemin_sinifi = 'ZB'
        elif vs30_val >= 360: zemin_sinifi = 'ZC'
        elif vs30_val >= 180: zemin_sinifi = 'ZD'
        else: zemin_sinifi = 'ZE'
        zemin_nedeni = f"Manuel Vs30 Hizi ({vs30_val} m/s)"
    elif cu30_val > 0:
        zemin_sinifi = 'ZC' if cu30_val > 250 else ('ZD' if cu30_val >= 70 else 'ZE')
        zemin_nedeni = f"Manuel Cu30 ({cu30_val} kPa)"
    else:
        zemin_sinifi = 'ZC' if n_ortalama > 50 else ('ZD' if n_ortalama >= 15 else 'ZE')
        zemin_nedeni = f"Harmonik (N60)30: {n_ortalama:.1f}"

    if ze_ozel_kosul and zemin_sinifi not in ['ZF', 'ZE']:
        zemin_sinifi, zemin_nedeni = 'ZE', "ZE Ozel Kil Kosulu"

    islem_sinifi = 'ZE' if zemin_sinifi == 'ZF' else zemin_sinifi

    # Spektrum Parametreleri
    fs_table = {'ZC': [(0.25, 1.3), (0.50, 1.2), (0.75, 1.1), (1.00, 1.0), (3.0, 1.0)], 'ZD': [(0.25, 1.6), (0.50, 1.4), (0.75, 1.2), (1.00, 1.1), (3.0, 1.0)], 'ZE': [(0.25, 2.5), (0.50, 1.7), (0.75, 1.2), (1.00, 0.9), (3.0, 0.8)]}
    f1_table = {'ZC': [(0.10, 1.5), (0.20, 1.5), (0.30, 1.5), (0.40, 1.5), (3.0, 1.4)], 'ZD': [(0.10, 2.4), (0.20, 2.2), (0.30, 2.0), (0.40, 1.9), (3.0, 1.7)], 'ZE': [(0.10, 4.2), (0.20, 3.3), (0.30, 2.8), (0.40, 2.4), (3.0, 2.0)]}

    Fs = np.interp(ss_val, [p[0] for p in fs_table[islem_sinifi]], [p[1] for p in fs_table[islem_sinifi]])
    F1 = np.interp(s1_val, [p[0] for p in f1_table[islem_sinifi]], [p[1] for p in f1_table[islem_sinifi]])

    SDS, SD1 = ss_val * Fs, s1_val * F1
    TA, TB = 0.2 * (SD1 / SDS), SD1 / SDS
    T_vals = np.linspace(0, 3.0, 300)
    Sae_vals = [SDS * (0.4 + 0.6 * (T / TA)) if T < TA else (SDS if T <= TB else SD1 / T) for T in T_vals]

    # Iyilestirme ve Nihai Guvenlik
    CSR_ham = 0.65 * pga_val * (df['Sigma_v'] / df['Sigma_ve']) * rd
    FS_ham = df['CRR'] / CSR_ham.replace(0, 0.001)
    
    kil_sarti = (df['PI'] > 12) | (df['Zemin_Sinifi'].str.contains('CH|CL', case=False, na=False)) if kati_filtre_aktif else pd.Series(False, index=df.index) 
    FS_ham = np.where(kil_sarti | (df['Derinlik_m'] <= df['GYS_m']) | (df['Derinlik_m'] > 20.0), 2.0, FS_ham)
    
    siv_mask_ham = (FS_ham < 1.10) & (df['N160cs'] < 30) & (df['Derinlik_m'] <= 20.0)
    iyilestirme_derinligi = df[siv_mask_ham]['Derinlik_m'].max() if siv_mask_ham.any() else 0.0

    Ar = min(0.60, (np.pi * (tasarim_capi / 200.0)**2) / (tasarim_grid**2)) if iyilestirme_aktif else 0.0
    KG = 1.0 / (Ar * 15.0 + 1.0 - Ar) 

    df['CSR'] = CSR_ham * KG
    df['FS'] = df['CRR'] / df['CSR'].replace(0, 0.001)
    df.loc[kil_sarti | (df['Derinlik_m'] <= df['GYS_m']) | (df['Derinlik_m'] > 20.0), 'FS'] = 2.0
    df['FS'] = np.clip(df['FS'], 0.0, 2.0)

    sivilasma_mask = (df['FS'] < 1.10) & (df['N160cs'] < 30) & (df['Derinlik_m'] <= 20.0)
    ev_perc = (1.5 * np.exp(-0.025 * df['N160cs']) / np.maximum(df['FS'], 0.4)) / 100.0
    df['Tabaka_Oturmasi_cm'] = np.where(sivilasma_mask, ev_perc * 150.0, 0.0)
    
    kuyu_oturmalari = df.groupby('Sondaj_No')['Tabaka_Oturmasi_cm'].sum().reset_index().rename(columns={'Tabaka_Oturmasi_cm': 'Toplam_Oturma_cm'})
    kuyu_oturmalari = pd.merge(kuyu_oturmalari, df.groupby('Sondaj_No')[['X_Koordinat_m', 'Y_Koordinat_m']].first().reset_index(), on='Sondaj_No')

    df['Renk'] = df['FS'].apply(lambda fs: 'red' if fs < 1.0 else ('orange' if fs < 1.1 else 'green'))

    max_oturma = kuyu_oturmalari['Toplam_Oturma_cm'].max() if not kuyu_oturmalari.empty else 0
    toplam_kolon_sayisi = int(proje_alani / (tasarim_grid**2)) if iyilestirme_aktif and iyilestirme_derinligi > 0 else 0
    toplam_metraj = toplam_kolon_sayisi * iyilestirme_derinligi
    toplam_maliyet = toplam_metraj * birim_fiyat

    sonuclar = {
        'zemin_sinifi': zemin_sinifi,
        'zemin_nedeni': zemin_nedeni,
        'Fs': Fs, 'F1': F1, 'SDS': SDS, 'SD1': SD1,
        'TA': TA, 'TB': TB, 'T_vals': T_vals, 'Sae_vals': Sae_vals,
        'tahmini_vs30_ort': tahmini_vs30_ort,
        'tahmini_cu30_ort': tahmini_cu30_ort,
        'max_oturma': max_oturma,
        'iyilestirme_derinligi': iyilestirme_derinligi,
        'Ar': Ar,
        'toplam_kolon_sayisi': toplam_kolon_sayisi,
        'toplam_metraj': toplam_metraj,
        'toplam_maliyet': toplam_maliyet
    }

    return df, kuyu_oturmalari, sonuclar