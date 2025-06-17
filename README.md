# WT3 (Wolf of Trading Tokens in TEE)

An autonomous trading AI agent powered by Oasis Protocol's secure TEE infrastructure, executing strategies on Hyperliquid with integrated social intelligence.

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
- Currently encrypted for proprietary strategy protection (open-source version planned)

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
./scripts/docker-run.sh build
```

4. Start services locally:
```bash
./scripts/docker-run.sh start
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

### Production Deployment

1. Build and push Docker images:
```bash
docker build -t yourusername/wt3 .
docker build -t yourusername/wt3-signal -f Dockerfile.signal .
docker push yourusername/wt3
docker push yourusername/wt3-signal
```

2. Set ROFL secrets:
```bash
echo -n "your_value" | oasis rofl secret set SECRET_NAME -
```

3. Build ROFL deployment:
```bash
oasis rofl build --deployment mainnet
```

4. Update ROFL deployment:
```bash
oasis rofl update --deployment mainnet
```

The deployment creates a `.orc` file that must be deployed to your Oasis node.

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
The trading strategy within the signal service is currently encrypted to protect proprietary algorithms. We plan to release an open-source reference strategy that can be used as a template for custom implementations.

## Project Structure

```
wt3/
├── src/
│   ├── wt3/                        # Main trading agent
│   │   ├── __main__.py             # Entry point and main loop
│   │   ├── core/                   # Core trading logic
│   │   ├── clients/                # API clients
│   │   └── prompts/                # Social media templates
│   └── signal_service/             # Signal generation (encrypted)
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