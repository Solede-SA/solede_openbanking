# Solede OpenBanking

Frappe app for ACube Open Banking API integration. This app enables seamless integration with European banks through PSD2 Open Banking standards.

## Features

- **JWT Token Authentication** - Automatic token generation and renewal (24-hour validity)
- **Business Registry Management** - Create and manage Business Registry per company
- **Bank Account Connection** - OAuth-style flow for bank authorization
- **Multi-Account Support** - Display and manage multiple authorized bank accounts
- **Company-Based Configuration** - Separate settings for each company
- **Automatic Return URL** - Smart redirect after bank authorization

## Installation

1. Get the app:
```bash
bench get-app https://github.com/YOUR_USERNAME/solede_openbanking.git
```

2. Install on site:
```bash
bench --site YOUR_SITE install-app solede_openbanking
```

## Configuration

### 1. OpenBanking Settings

Navigate to **OpenBanking Settings** and create a new document for your company.

Fill in the following fields:

- **Company**: Select your company
- **Common API URL**: Authentication endpoint (e.g., `https://common-sandbox.api.acubeapi.com`)
- **Open Banking API URL**: Open Banking operations endpoint (e.g., `https://ob-sandbox.api.acubeapi.com`)
- **Email**: Your ACube account email
- **Password**: Your ACube account password

### 2. Company Setup

Ensure your Company document has a valid **Tax ID** (Partita IVA) configured, as this is used as the fiscal ID for the Business Registry.

## Usage

### Step 1: Generate Token

Click the **Generate Token** button to authenticate and generate a JWT token. The token is valid for 24 hours and will auto-renew when needed.

### Step 2: Create Business Registry

Click **Create Business Registry** to register your company with ACube Open Banking.

⚠️ **Note**: This operation incurs a fee from ACube.

The system will use:
- Fiscal ID from Company's Tax ID field
- Business Name from Company's name
- Email from OpenBanking Settings

### Step 3: Connect Bank Account

Once the Business Registry is created, click **Connect Bank Account**.

You can specify:
- **Bank Manager Email** (optional): Email of the person managing the connection
- **Consent Days** (1-180): Duration of the bank consent (default: 180 days)

The system automatically uses the current page URL as the return URL, so you'll be redirected back after authorization.

A new window will open where you can:
1. Select your bank
2. Authenticate with your bank credentials
3. Authorize account access

### Step 4: Refresh Accounts

After completing the bank authorization, click **Refresh Accounts** to retrieve and display all authorized bank accounts in the "Authorized Bank Accounts" tab.

### Additional Operations

- **Get Business Registry Info**: View current Business Registry details including fiscal ID, email, status, and sub-account ID

## API Endpoints Used

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/login` | POST | Generate authentication token |
| `/business-registry` | POST | Create new Business Registry |
| `/business-registry/{fiscalId}` | GET | Retrieve Business Registry information |
| `/business-registry/{fiscalId}/connect` | POST | Start bank connection process |
| `/business-registry/{fiscalId}/accounts` | GET | List authorized bank accounts |

## Data Model

### OpenBanking Settings
- Company (Link to Company)
- API URLs (Common API and OpenBanking API)
- Credentials (Email and Password)
- Business Registry Status
- Token Information (Access Token, Created At, Expires At)
- Authorized Bank Accounts (Child Table)

### OpenBanking Account (Child Table)
- UUID
- Account ID
- IBAN
- Account Name
- Provider Name
- Provider Country
- Nature
- Balance
- Currency Code
- Enabled Status
- Consent Expiration Date

## Code Structure

```
solede_openbanking/
├── api/
│   ├── authentication.py       # JWT token management
│   └── business_registry.py    # Business Registry and account operations
├── solede_openbanking/
│   └── doctype/
│       ├── openbanking_settings/
│       │   ├── openbanking_settings.json
│       │   ├── openbanking_settings.py
│       │   └── openbanking_settings.js
│       └── openbanking_account/
│           ├── openbanking_account.json
│           └── openbanking_account.py
└── README.md
```

## Key Functions

### Authentication (`authentication.py`)

- `generate_token(company)` - Generate new JWT token
- `get_valid_token(company)` - Get valid token (auto-renews if expired)
- `decode_token_payload(token)` - Decode JWT payload for debugging

### Business Registry (`business_registry.py`)

- `create_business_registry(company, password)` - Create Business Registry
- `get_business_registry_info(company)` - Retrieve Business Registry details
- `start_connect_request(company, return_url, bank_manager_email, days)` - Start bank connection
- `get_accounts(company)` - Retrieve and populate authorized accounts

## Environment

- **Sandbox**: `https://ob-sandbox.api.acubeapi.com`
- **Production**: `https://ob.api.acubeapi.com`

## Security Notes

- Passwords are stored encrypted using Frappe's password field
- JWT tokens are stored in the database and auto-renewed
- All API calls use Bearer token authentication
- Business Registry fiscal ID is retrieved from Company's Tax ID

## Error Handling

The app follows DRY and KISS principles:
- No fallback mechanisms - errors are always shown to users
- Clear error messages from API responses
- Detailed logging for debugging

## Requirements

- Frappe Framework v15+
- ERPNext v15+
- Python 3.10+
- Valid ACube Open Banking account
- Company with valid Tax ID (Partita IVA)

## Contributing

This app uses `pre-commit` for code formatting and linting. Please [install pre-commit](https://pre-commit.com/#installation) and enable it for this repository:

```bash
cd apps/solede_openbanking
pre-commit install
```

Pre-commit is configured to use the following tools for checking and formatting your code:

- ruff
- eslint
- prettier
- pyupgrade

## License

MIT

## Support

For issues and feature requests, please open an issue on GitHub.

## Credits

Developed with [Claude Code](https://claude.com/claude-code)
