import plotly.graph_objects as go
import numpy as np
from scipy.interpolate import griddata

def ciz_spektrum(T_vals, Sae_vals, TA, TB, etiket):
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=T_vals, y=Sae_vals, mode='lines', line=dict(color='cyan', width=3), fill='tozeroy', fillcolor='rgba(0, 255, 255, 0.1)', name="Tasarim Spektrumu"))
    fig.add_vline(x=TA, line_dash="dash", line_color="gray", annotation_text="TA")
    fig.add_vline(x=TB, line_dash="dash", line_color="gray", annotation_text="TB")
    fig.update_layout(title=f"Yatay Elastik Tasarim Spektrumu ({etiket})", xaxis_title="Periyot T (sn)", yaxis_title="Spektral Ivme Sae(T) [g]", template="plotly_dark", height=500)
    return fig

def ciz_3d(df, hedef_derinlik):
    fig = go.Figure()
    max_x_raw, max_y_raw = df['X_Koordinat_m'].max(), df['Y_Koordinat_m'].max()
    max_extent = max(max_x_raw, max_y_raw, 100)
    max_x, max_y = max(max_x_raw, max_extent * 0.4), max(max_y_raw, max_extent * 0.4)
    pad = max(10.0, max_extent * 0.05)

    # Zemin yüzeyini temsil eden taban düzlem
    fig.add_trace(go.Mesh3d(x=[-pad, max_x+pad, max_x+pad, -pad], y=[-pad, -pad, max_y+pad, max_y+pad], z=[0,0,0,0], i=[0,0], j=[1,2], k=[2,3], opacity=0.1, color='white', hoverinfo='none'))

    # Her benzersiz sondajın en üst noktasına kurumsal etiket basılması
    for sondaj in df['Sondaj_No'].unique():
        temp = df[df['Sondaj_No'] == sondaj].sort_values('Derinlik_m')
        
        # Kuyunun çizgisi ve derinlik boyunca katman noktaları
        fig.add_trace(go.Scatter3d(
            x=temp['X_Koordinat_m'], y=temp['Y_Koordinat_m'], z=-temp['Derinlik_m'], mode='lines+markers',
            marker=dict(size=6, color=temp['Renk'], line=dict(width=1, color='black')), line=dict(color='rgba(255,255,255,0.4)', width=5),
            text=[f"Sondaj: {s}<br>Zemin: {z}<br>FS: {f:.2f}<br>Oturma: {o:.2f} cm" for s,z,f,o in zip(temp['Sondaj_No'], temp['Zemin_Sinifi'], temp['FS'], temp['Tabaka_Oturmasi_cm'])], hoverinfo='text', name=sondaj
        ))
        
        # Tam zemin yüzeyi kotu (Z=0) için elit grafik tasarımı
        en_ust_nokta = temp.iloc[0]
        fig.add_trace(go.Scatter3d(
            x=[en_ust_nokta['X_Koordinat_m']], 
            y=[en_ust_nokta['Y_Koordinat_m']], 
            z=[0.0], 
            mode='text', 
            text=[f"<b>{sondaj}</b>"], # Kalın font ama kibar durması için HTML tag kullandık
            textposition='top center',
            textfont=dict(
                family='Helvetica Neue, Helvetica, Arial, sans-serif', # Premium kurumsal yazı tipi
                size=12, 
                color='#E0E0E0' # Mat gümüş/beyaz tonu, gözü yormaz ve elit durur
            ),
            showlegend=False,
            hoverinfo='none'
        ))

    # Belirli derinlikteki sivilasma risk (izohips) dilimi
    dilim_df = df[(df['Derinlik_m'] >= hedef_derinlik - 2.5) & (df['Derinlik_m'] <= hedef_derinlik + 2.5)].dropna(subset=['X_Koordinat_m', 'Y_Koordinat_m', 'FS'])
    if len(dilim_df['Sondaj_No'].unique()) >= 3: 
        isi_veri = dilim_df.sort_values(by="Derinlik_m", key=lambda x: abs(x - hedef_derinlik)).groupby('Sondaj_No').first().reset_index()
        X_grid, Y_grid = np.meshgrid(np.linspace(-pad, max_x+pad, 50), np.linspace(-pad, max_y+pad, 50))
        grid_z = griddata(isi_veri[['X_Koordinat_m', 'Y_Koordinat_m']].values, isi_veri['FS'].values, (X_grid, Y_grid), method='nearest')
        fig.add_trace(go.Surface(x=X_grid, y=Y_grid, z=np.full((50, 50), -hedef_derinlik), surfacecolor=grid_z, colorscale=[[0, 'red'], [0.25, 'orange'], [0.5, 'green'], [1.0, 'darkgreen']], cmin=0.5, cmax=2.0, opacity=0.6, showscale=True))

    fig.update_layout(template="plotly_dark", margin=dict(l=0, r=0, b=0, t=0), height=700, scene=dict(aspectmode='manual', aspectratio=dict(x=1, y=1, z=0.5)))
    return fig

def ciz_2d(df, secili_kuyular):
    fig = go.Figure()
    kesit_df = df[df['Sondaj_No'].isin(secili_kuyular)]
    kuyu_konumlari = kesit_df.groupby('Sondaj_No')['X_Koordinat_m'].mean().sort_values()
    
    px_vals, pz_vals, vfs = [], [], []
    for kuyu in kuyu_konumlari.index:
        for _, row in kesit_df[kesit_df['Sondaj_No'] == kuyu].iterrows():
            px_vals.append(kuyu_konumlari[kuyu]); pz_vals.append(-row['Derinlik_m']); vfs.append(row['FS'])

    if len(px_vals) > 4:
        grid_x, grid_z = np.meshgrid(np.linspace(min(px_vals), max(px_vals), 100), np.linspace(min(pz_vals), 0, 100))
        fig.add_trace(go.Contour(x=np.linspace(min(px_vals), max(px_vals), 100), y=np.linspace(min(pz_vals), 0, 100), z=griddata((px_vals, pz_vals), vfs, (grid_x, grid_z), method='linear'), colorscale=[[0, 'red'], [0.3, 'orange'], [0.6, 'green'], [1.0, 'darkgreen']], zmin=0.5, zmax=2.0, opacity=0.45, showscale=True))

    for kuyu in kuyu_konumlari.index:
        temp = kesit_df[kesit_df['Sondaj_No'] == kuyu]
        fig.add_trace(go.Scatter(x=[kuyu_konumlari[kuyu]]*len(temp), y=-temp['Derinlik_m'], mode='lines+markers+text', marker=dict(size=18, symbol='square', color=temp['Renk'], line=dict(width=1, color='white')), line=dict(color='gray', width=4), text=temp['Zemin_Sinifi'], textposition="middle right", name=kuyu, customdata=temp[['FS']]))

    fig.update_layout(template="plotly_dark", height=600, xaxis=dict(tickvals=kuyu_konumlari.values, ticktext=kuyu_konumlari.index.tolist()), showlegend=False)
    return fig

def ciz_vaziyet(kuyu_oturmalari):
    fig = go.Figure()
    x_min, x_max = kuyu_oturmalari['X_Koordinat_m'].min(), kuyu_oturmalari['X_Koordinat_m'].max()
    y_min, y_max = kuyu_oturmalari['Y_Koordinat_m'].min(), kuyu_oturmalari['Y_Koordinat_m'].max()
    pad_x, pad_y = max(10, (x_max - x_min)*0.1), max(10, (y_max - y_min)*0.1)
    
    xi = np.linspace(x_min - pad_x, x_max + pad_x, 100)
    yi = np.linspace(y_min - pad_y, y_max + pad_y, 100)
    X_grid, Y_grid = np.meshgrid(xi, yi)
    
    Z_grid = griddata(kuyu_oturmalari[['X_Koordinat_m', 'Y_Koordinat_m']].values, kuyu_oturmalari['Toplam_Oturma_cm'].values, (X_grid, Y_grid), method='linear')

    fig.add_trace(go.Contour(x=xi, y=yi, z=Z_grid, colorscale='Reds', contours=dict(showlabels=True, labelfont=dict(size=14, color='white')), colorbar=dict(title="Oturma (cm)", thickness=20)))
    fig.add_trace(go.Scatter(x=kuyu_oturmalari['X_Koordinat_m'], y=kuyu_oturmalari['Y_Koordinat_m'], mode='markers+text', marker=dict(size=14, color='black', symbol='cross', line=dict(color='white', width=1)), text=kuyu_oturmalari['Sondaj_No'] + "<br>" + kuyu_oturmalari['Toplam_Oturma_cm'].round(1).astype(str) + " cm", textposition="top center", textfont=dict(color='white', size=13, weight='bold')))

    fig.update_layout(template="plotly_dark", height=750)
    return fig
