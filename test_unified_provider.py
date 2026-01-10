"""Quick test of unified provider"""
import os

os.environ['ZERODHA_API_KEY'] = 'wialyvtiwscm10th'
os.environ['ZERODHA_API_SECRET'] = '2f1k69xaf2ju3aksepmt5fzdfrvy9mi1'

from app.providers import get_data_provider

print("\n" + "="*60)
print("UNIFIED PROVIDER TEST")
print("="*60)

provider = get_data_provider()

print(f"\n1. Data Source: {provider.get_data_source()}")
print(f"2. Zerodha Available: {provider.zerodha.kite is not None}")
print(f"3. Zerodha Authenticated: {provider.use_zerodha}")
print(f"4. Access Token Present: {provider.zerodha.access_token is not None}")

if provider.zerodha.access_token:
    print(f"5. Token (first 20 chars): {provider.zerodha.access_token[:20]}...")

print("\n" + "-"*60)
print("Testing get_indices_quote()...")
print("-"*60)

try:
    indices = provider.get_indices_quote()
    print(f"\n✓ Success! Got {len(indices)} indices")
    for name, data in indices.items():
        price = data.get('price', 'N/A')
        change = data.get('change_percent', 'N/A')
        print(f"  {name}: {price} ({change}%)")
except Exception as e:
    print(f"\n✗ Error: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "="*60)
