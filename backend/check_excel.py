import pandas as pd
try:
    df = pd.read_excel('data/formosan_pairs_paiwan.xlsx')
    print(df.columns.tolist())
    print(df.head(1))
except Exception as e:
    print(e)
