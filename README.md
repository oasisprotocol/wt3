# WT3 (Wolf of Trading Tokens in TEE)

An autonomous trading AI agent powered by Oasis secure TEE infrastructure, executing strategies on Hyperliquid with integrated social intelligence.

## Overview

WT3 is a sophisticated trading system that combines:
- Secure execution within Intel TDX trusted enclaves via the Oasis ROFL framework
- Automated trading strategies with risk management
- AI-powered social media integration for market commentary
- Hourly trading cycles with position management
- Real-time market analysis and signal generation

The system operates autonomously, executing trades based on proprietary signals while maintaining an active social media presence to share trading insights and market analysis.

## Architecture

WT3 consists of two main components running as containerized services:

### Signal Service
- Generates trading signals based on market analysis
- Provides REST API endpoints for signal consumption
- Integrates with Predictoor for AI-driven market predictions
- Includes both encrypted proprietary strategy and open-source example
- Automatic fallback to example service if primary is unavailable

### WT3 Main Agent
- Executes trades on Hyperliquid exchange
- Manages positions with automated stop-loss and take-profit
- Posts hourly trading recaps on Twitter/X
- Responds to social media mentions
- Maintains persistent trade and conversation history

Both services run within the Oasis ROFL framework, ensuring secure key management and trusted execution.

## Prerequisites

- Docker and Docker Compose
- Python 3.11+
- Oasis CLI tools (`oasis` command)
- Age encryption tool (for signal service decryption)
- Understanding of trading, blockchain and TEEs

## Installation

### Local Development Setup

For local development without Docker or ROFL/TEE requirements:

1. Clone the repository:
```bash
git clone https://github.com/oasisprotocol/wt3.git
cd wt3
```

2. Create and activate a Python virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install --upgrade pip
pip install -r requirements.signal.txt
```

4. Modify the ROFL clients to use local keypairs:
   - In `src/wt3/clients/rofl.py` and `src/signal_service_example/clients/rofl.py`
   - Replace the `get_keypair` function to return a private key from environment:
   ```python
   import os

   def get_keypair(key_id: str = WT3_TRADING_KEY):
       private_key = os.getenv("PRIVATE_KEY")
       if not private_key:
           raise ValueError("PRIVATE_KEY environment variable not set")

       account = Account.from_key(private_key)
       return private_key, account.address
   ```

5. Create a `.env` file with your configuration:

```bash
# Private key for local development (use a test key, never real funds!)
PRIVATE_KEY=0xYOUR_PRIVATE_KEY_HERE

# Signal Service URL
SIGNAL_SERVICE_URL=http://localhost:8001

# API Keys
GROK_API_KEY=your_grok_api_key
TWITTER_BEARER_TOKEN=your_twitter_bearer_token
TWITTER_API_KEY=your_twitter_api_key
TWITTER_API_SECRET=your_twitter_api_secret
TWITTER_ACCESS_TOKEN=your_twitter_access_token
TWITTER_ACCESS_TOKEN_SECRET=your_twitter_access_token_secret
```

6. Run the signal service in one terminal:
```bash
python -m src.signal_service_example
```

7. Run the main WT3 agent in another terminal:
```bash
python -m src.wt3
```

**Note**: For local development, you'll need to bypass the ROFL socket connection. The easiest way is to modify the `rofl.py` files as described above.

### Production Deployment

1. Clone the repository:
```bash
git clone https://github.com/oasisprotocol/wt3.git
cd wt3
```

2. Set up environment variables:
```bash
cp .env.example .env
# Edit .env with your configuration
```

3. Build Docker images:
```bash
docker build -t yourusername/wt3:latest .
docker build -t yourusername/wt3-signal:latest -f Dockerfile.signal .
```

4. Push images to Docker Hub and update compose.yaml:
```bash
# Push images
docker push yourusername/wt3
docker push yourusername/wt3-signal

# Get the image digests
docker inspect --format='{{index .RepoDigests 0}}' yourusername/wt3:latest
docker inspect --format='{{index .RepoDigests 0}}' yourusername/wt3-signal:latest

# Update compose.yaml with your images and sha256 digests
# Example:
# wt3:
#   image: docker.io/yourusername/wt3@sha256:YOUR_DIGEST_HERE
# signal-service:
#   image: docker.io/yourusername/wt3-signal@sha256:YOUR_DIGEST_HERE
```

5. Initialize and create ROFL app:
```bash
# Initialize ROFL
oasis rofl init

# Create ROFL app
oasis rofl create
```

6. Build and update ROFL deployment:
```bash
# Build ROFL app
oasis rofl build

# Update ROFL deployment
oasis rofl update
```

7. Deploy to ROFL node:
```bash
# The build process creates a .orc file
# Deploy this file to your Oasis node following the node operator guide
# See: https://docs.oasis.io/node/run-your-node/rofl-node
```

## Configuration

### Environment Variables

Required variables in `.env`:

- `GROK_API_KEY` - API key for AI content generation
- `TWITTER_BEARER_TOKEN` - Twitter API bearer token
- `TWITTER_API_KEY` - Twitter API key
- `TWITTER_API_SECRET` - Twitter API secret
- `TWITTER_ACCESS_TOKEN` - Twitter access token
- `TWITTER_ACCESS_TOKEN_SECRET` - Twitter access token secret
- `SIGNAL_SERVICE_URL` - Internal signal service endpoint
- `AGE_PRIVATE_KEY` - Private key for signal service decryption

### Social Media Configuration

1. Copy the template file:
```bash
cp social_prompts_template.py social_prompts.py
```

2. Edit `social_prompts.py` to customize AI-generated content prompts


## Deployment

### Local Development

Use the provided Docker script for local development:

```bash
# Build images
./scripts/docker-run.sh build

# Start containers
./scripts/docker-run.sh start

# View logs
./scripts/docker-run.sh logs

# Stop containers
./scripts/docker-run.sh stop
```

## Signal Service Example

The `signal_service_example` provides an open-source momentum-based trading strategy that serves as:
- A fallback when the primary encrypted signal service is unavailable
- A template for developing custom trading strategies
- A demonstration of the signal service API implementation

### Strategy Details
The example strategy combines:
- 14-period RSI for overbought/oversold conditions
- 20-period and 50-period SMAs for trend confirmation
- Dynamic position sizing based on account balance
- Maximum 5x leverage with minimum $100 trade size

### Running the Example Service
The signal_service_example automatically runs when:
1. The encrypted signal service fails to decrypt (missing AGE_PRIVATE_KEY)
2. The primary service is unavailable or unhealthy
3. You explicitly start it without the encrypted service

## API Reference

### Signal Service Endpoints

#### Health Check
```
GET /health
```
Returns service status.

#### Get Trading Signal
```
GET /signal/<coin>
```
Returns trading signal for specified cryptocurrency.

**Response Format:**
```json
{
    "timestamp": 1234567890,
    "trade_decision": {
        "action": "open",
        "direction": "long",
        "confidence": 0.85,
        "coin": "BTC",
        "strategy": {
            "position_size_coin": 0.1,
            "leverage": 2.0,
            "stop_loss": 50000.0,
            "take_profit": 55000.0
        }
    },
    "current_position": {
        "size": 0.1,
        "direction": "LONG",
        "entry_price": 50000.0
    }
}
```

## Security

### Trusted Execution Environment

WT3 runs within Intel TDX enclaves via the Oasis ROFL framework, providing:
- Secure key management
- Protected execution environment
- Attestation capabilities
- Isolation from host system

### Encryption

- Signal service code is encrypted using Age encryption
- Secrets are encrypted in ROFL configuration
- All sensitive API keys are stored as encrypted secrets
- Private keys never leave the TEE environment

### Signal Service Protection

The trading strategy within the signal service is encrypted to protect proprietary algorithms. An open-source example strategy (`signal_service_example`) is included as a fallback and template for custom implementations.

## Project Structure

```
wt3/
├── src/
│   ├── wt3/                        # Main trading agent
│   │   ├── __main__.py             # Entry point and main loop
│   │   ├── core/                   # Core trading logic
│   │   ├── clients/                # API clients
│   │   └── prompts/                # Social media templates
│   ├── signal_service/             # Signal generation (encrypted)
│   └── signal_service_example/     # Open-source example strategy
├── scripts/                        # Deployment and utility scripts
├── data/                           # Configuration and deployment files
├── tests/                          # Testing utilities
├── requirements.txt                # Python dependencies for main agent
├── requirements.signal.txt         # Python dependencies for signal service
├── Dockerfile                      # Main agent container definition
├── Dockerfile.signal               # Signal service container definition
├── compose.yaml                    # Docker Compose configuration
├── rofl.yaml                       # ROFL deployment configuration
├── signal_service.tar.gz.age       # Encrypted signal service archive
├── .env.example                    # Environment variables template
└── social_prompts_template.py      # Social media prompts template
```

## Data Persistence

WT3 maintains the following persistent data:
- `trade_history.csv` - Complete trading history
- `conversation_history.json` - Social media interactions
- Position state and market data

## License

This project is licensed under the Apache License 2.0 - see the [LICENSE](LICENSE) file for details.

## Disclaimer

This software is for educational purposes only. Use at your own risk. The authors are not responsible for any financial losses incurred through the use of this software.