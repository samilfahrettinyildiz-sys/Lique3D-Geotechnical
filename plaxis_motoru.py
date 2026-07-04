def plaxis_makrosu_uret(df, kuyu_adi="SK-01"):
    # Makronun en başındaki sabit bağlantı kodları
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

    # Tabloyu okuyup dinamik olarak PLAXIS'e malzeme ve tabaka ekleme döngüsü
    script += "# --- ZEMIN PARAMETRELERI VE TABAKALAR ---\n"
    
    for index, row in df.iterrows():
        derinlik = row['Derinlik_m']
        zemin_sinifi = row['Zemin_Sinifi']
        gamma = row['Gamma_Tasarim']
        cu = row['Cu_Tasarim'] if pd.notna(row['Cu_Tasarim']) else 0.0
        phi = row['Phi_Acisi'] if pd.notna(row['Phi_Acisi']) else 0.0
        e_mod = row['E_Modulu']
        
        # PLAXIS'te Drain type ayarı: Cu varsa Drenajsız (Undrained B - 3), yoksa Drenajlı (Drained - 1)
        drainage = 3 if cu > 0 else 1
        
        mat_adi = f"Mat_{index+1}_{zemin_sinifi}"
        
        # Python scriptine PLAXIS malzeme yaratma kodunu yazdırıyoruz
        script += f"{mat_adi} = g_i.soilmat('Identification', '{zemin_sinifi} ({derinlik}m)', "
        script += f"'SoilModel', 2, 'DrainageType', {drainage}, "
        script += f"'gammaUnsat', {gamma}, 'gammaSat', {gamma + 1.0}, "
        script += f"'Eref', {e_mod}, 'nu', 0.35, "
        script += f"'cref', {cu if cu > 0 else 1.0}, 'phi', {phi})\n"
        
        # PLAXIS'e tabaka ekle ve sınırını belirle
        script += f"g_i.soillayer(bh)\n"
        # Not: PLAXIS'te ilk tabaka 0'dır, ona göre indeks ayarlıyoruz
        script += f"g_i.set(bh.SoilLayers[{index}].Bottom, -{derinlik})\n"
        # Malzemeyi tabakaya ata
        script += f"g_i.setmaterial(bh.SoilLayers[{index}], {mat_adi})\n\n"
        
    script += "print('Lique3D Verileri PLAXIS 2D Ortamina Basariyla Aktarildi!')\n"
    
    # Bu metni byte (dosya) formatına çevirip döndürüyoruz
    return script.encode('utf-8')