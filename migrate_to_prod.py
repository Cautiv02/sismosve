"""Script para copiar eventos locales a produccion."""
import sys
import requests

LOCAL_URL  = "http://localhost:8000/api/registro?limit=1000"
PROD_URL   = "https://sismosvenezuela.com/api/registro/import"
IMPORT_KEY = "sismos2024secret"  # debe coincidir con IMPORT_KEY en Railway

def main():
    print("Leyendo eventos locales...")
    r = requests.get(LOCAL_URL)
    r.raise_for_status()
    data = r.json()
    total_local = len(data.get("features", []))
    print(f"  {total_local} eventos encontrados localmente")

    print("Enviando a produccion...")
    r2 = requests.post(f"{PROD_URL}?key={IMPORT_KEY}", json=data)
    r2.raise_for_status()
    result = r2.json()
    print(f"  Importados: {result['imported']} nuevos")
    print(f"  Total en produccion: {result['total']}")

if __name__ == "__main__":
    main()
