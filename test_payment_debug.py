#!/usr/bin/env python3
"""
Script di debug per verificare configurazione e testare pagamenti OpenBanking
"""

import sys
import json

# Setup Frappe
sys.path.append('/Users/lorenzo/aaa_codice/Frappe/frappe-bench/apps')

import frappe

def main():
    frappe.init(site='mysite.local')
    frappe.connect()
    frappe.set_user('Administrator')

    from solede_openbanking.api.debug_payment import verify_settings

    # Trova la prima company con OpenBanking Settings
    companies = frappe.get_all("OpenBanking Settings", fields=["name"])

    if not companies:
        print("ERRORE: Nessuna OpenBanking Settings trovata")
        return

    company = companies[0].name
    print(f"\n{'='*80}")
    print(f"VERIFICA CONFIGURAZIONE PER COMPANY: {company}")
    print('='*80)

    result = verify_settings(company)

    print("\nRISULTATO:")
    print(json.dumps(result, indent=2))

    # Se ci sono account abilitati, testa la chiamata
    if result.get('success') and result.get('config', {}).get('accounts'):
        print(f"\n{'='*80}")
        print("TEST CHIAMATA API PAGAMENTO")
        print('='*80)

        from solede_openbanking.api.debug_payment import debug_payment_request

        first_account = result['config']['accounts'][0]
        account_uuid = first_account['uuid']

        print(f"\nUsando account UUID: {account_uuid}")
        print(f"IBAN: {first_account['iban']}")
        print(f"Systems: {first_account.get('systems', [])}")

        # Test con IBAN di esempio
        test_iban = "IT60X0542811101000000123456"

        payment_result = debug_payment_request(
            company=company,
            account_uuid=account_uuid,
            creditor_iban=test_iban,
            amount="10.00",
            use_instant=False
        )

        print("\nRISULTATO TEST PAGAMENTO:")
        print(json.dumps(payment_result, indent=2))

    frappe.db.commit()
    frappe.destroy()

if __name__ == "__main__":
    main()
