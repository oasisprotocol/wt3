"""
Momentum trading strategy for Signal Service Example.

This module provides functionality for generating trading signals based on
momentum indicators including RSI and moving averages. It implements a
systematic approach to identifying market momentum and generating trade
decisions with proper risk management.
"""

import logging
from typing import Dict, List, Optional

from ..clients.market_data import MarketDataClient
from ..clients.hl_client import HyperliquidClient
from ..clients.rofl import get_keypair

logger = logging.getLogger(__name__)

class StrategyError(Exception):
    """Base exception for strategy errors."""
    pass

class DataError(StrategyError):
    """Exception raised when data operations fail."""
    pass

class CalculationError(StrategyError):
    """Exception raised when calculations fail."""
    pass

class MomentumStrategy:
    """
    Momentum trading strategy using RSI and moving averages.
    
    Strategy Rules:
    - Buy Signal: RSI crosses above 30 (oversold) AND price above 20-period SMA
    - Sell Signal: RSI crosses below 70 (overbought) OR price below 20-period SMA
    - Strong Buy: RSI < 20 AND price bouncing off 50-period SMA
    - Strong Sell: RSI > 80
    """
    
    def __init__(self):
        private_key, public_address = get_keypair()
        logger.info(f"Initialized momentum strategy with wallet address: {public_address}")
        
        self.market_client = MarketDataClient()
        self.hl_client = HyperliquidClient(private_key)
        
        self.fast_sma_period = 20
        self.slow_sma_period = 50
        self.rsi_period = 14
        self.rsi_oversold = 30
        self.rsi_overbought = 70
        
        self.risk_per_trade = 0.02
        self.reward_risk_ratio = 3.0
        self.max_leverage = 5.0
        self.min_trade_size_usd = 100.0
    
    async def get_signal(self, coin: str) -> Dict:
        """Generate trading signal for a coin."""
        try:
            async with self.market_client:
                klines = await self.market_client.get_klines(coin, '1h', 100)
                current_price = await self.market_client.get_current_price(coin)
                
                closes = [k['close'] for k in klines]
                
                fast_sma = self._calculate_sma(closes, self.fast_sma_period)
                slow_sma = self._calculate_sma(closes, self.slow_sma_period)
                rsi_values = self._calculate_rsi(closes, self.rsi_period)
                
                current_fast_sma = fast_sma[-1]
                current_slow_sma = slow_sma[-1]
                current_rsi = rsi_values[-1]
                prev_rsi = rsi_values[-2]
                
                signal = self._generate_momentum_signal(
                    current_price, current_fast_sma, current_slow_sma,
                    current_rsi, prev_rsi
                )
                
                position_size = self.hl_client.get_current_position(coin)
                account_balance = self.hl_client.get_account_balance()
                
                trade_decision = await self._make_trade_decision(
                    signal, position_size, coin, current_price, account_balance
                )
                
                if trade_decision:
                    logger.info(f"Generated {trade_decision['action']} signal for {coin}: {trade_decision['direction']} @ ${current_price:,.2f}")
                
                return {
                    "trade_decision": trade_decision,
                    "current_position": self._format_position(position_size, coin)
                }
                
        except Exception as e:
            error_msg = f"Strategy error: {str(e)}"
            logger.error(error_msg)
            raise StrategyError(error_msg)
    
    def _calculate_sma(self, prices: List[float], period: int) -> List[float]:
        """Calculate Simple Moving Average."""
        sma_values = []
        for i in range(len(prices)):
            if i < period - 1:
                sma_values.append(None)
            else:
                sma = sum(prices[i - period + 1:i + 1]) / period
                sma_values.append(sma)
        return sma_values
    
    def _calculate_rsi(self, prices: List[float], period: int = 14) -> List[float]:
        """Calculate Relative Strength Index."""
        if len(prices) < period + 1:
            raise CalculationError(f"Not enough data for RSI calculation: need {period + 1}, got {len(prices)}")
        
        deltas = [prices[i] - prices[i-1] for i in range(1, len(prices))]
        
        gains = [d if d > 0 else 0 for d in deltas]
        losses = [-d if d < 0 else 0 for d in deltas]
        
        avg_gain = sum(gains[:period]) / period
        avg_loss = sum(losses[:period]) / period
        
        rsi_values = []
        
        for i in range(period, len(deltas) + 1):
            if avg_loss == 0:
                rsi = 100
            else:
                rs = avg_gain / avg_loss
                rsi = 100 - (100 / (1 + rs))
            
            rsi_values.append(rsi)
            
            if i < len(deltas):
                avg_gain = ((avg_gain * (period - 1)) + gains[i]) / period
                avg_loss = ((avg_loss * (period - 1)) + losses[i]) / period
        
        return rsi_values
    
    def _generate_momentum_signal(
        self,
        current_price: float,
        fast_sma: float,
        slow_sma: float,
        current_rsi: float,
        prev_rsi: float
    ) -> Dict:
        """Generate trading signal based on momentum indicators."""
        signal = {
            'direction': None,
            'confidence': 0.0,
            'reason': ''
        }
        
        rsi_cross_above_oversold = prev_rsi <= self.rsi_oversold and current_rsi > self.rsi_oversold
        rsi_cross_below_overbought = prev_rsi >= self.rsi_overbought and current_rsi < self.rsi_overbought
        
        if current_rsi < 20 and current_price > slow_sma * 0.98:
            signal['direction'] = 'long'
            signal['confidence'] = 0.9
            signal['reason'] = 'Strong oversold with SMA support'
        
        elif current_rsi > 80:
            signal['direction'] = 'short'
            signal['confidence'] = 0.9
            signal['reason'] = 'Extreme overbought condition'
        
        elif rsi_cross_above_oversold and current_price > fast_sma:
            signal['direction'] = 'long'
            signal['confidence'] = 0.7
            signal['reason'] = 'RSI bounce from oversold above SMA'
        
        elif rsi_cross_below_overbought or (current_price < fast_sma and current_rsi > 50):
            signal['direction'] = 'short'
            signal['confidence'] = 0.7
            signal['reason'] = 'RSI overbought or price below SMA'
        
        elif current_price > fast_sma and fast_sma > slow_sma and current_rsi > 40 and current_rsi < 60:
            signal['direction'] = 'long'
            signal['confidence'] = 0.5
            signal['reason'] = 'Uptrend momentum continuation'
        
        elif current_price < fast_sma and fast_sma < slow_sma and current_rsi > 40 and current_rsi < 60:
            signal['direction'] = 'short'
            signal['confidence'] = 0.5
            signal['reason'] = 'Downtrend momentum continuation'
        
        return signal
    
    async def _make_trade_decision(
        self,
        signal: Dict,
        position_size: float,
        coin: str,
        current_price: float,
        account_balance: float
    ) -> Dict:
        """Make trade decision based on signal and current position."""
        if not signal['direction'] or signal['confidence'] < 0.5:
            return None
        
        risk_amount = account_balance * self.risk_per_trade
        
        if signal['confidence'] >= 0.8:
            stop_loss_pct = 0.01
        else:
            stop_loss_pct = 0.015
        
        position_size_usd = risk_amount / stop_loss_pct
        
        max_position_usd = account_balance * self.max_leverage
        position_size_usd = min(position_size_usd, max_position_usd)
        
        if position_size_usd < self.min_trade_size_usd:
            return None
        
        position_size_coin = position_size_usd / current_price
        
        if signal['direction'] == 'long':
            stop_loss = current_price * (1 - stop_loss_pct)
            take_profit = current_price * (1 + (stop_loss_pct * self.reward_risk_ratio))
        else:
            stop_loss = current_price * (1 + stop_loss_pct)
            take_profit = current_price * (1 - (stop_loss_pct * self.reward_risk_ratio))
        
        has_position = position_size != 0
        position_is_long = position_size > 0
        signal_is_long = signal['direction'] == 'long'
        
        if not has_position:
            action = 'open'
        elif (position_is_long and signal_is_long) or (not position_is_long and not signal_is_long):
            return None
        else:
            action = 'close_and_reverse'
        
        return {
            'action': action,
            'direction': signal['direction'],
            'confidence': signal['confidence'],
            'coin': coin,
            'strategy': {
                'position_size_coin': round(position_size_coin, 6),
                'leverage': round(position_size_usd / account_balance, 1),
                'stop_loss': round(stop_loss, 2),
                'take_profit': round(take_profit, 2)
            }
        }
    
    def _format_position(self, position_size: float, coin: str) -> Optional[Dict]:
        """Format position data for response."""
        if position_size == 0:
            return None
        
        return {
            'size': abs(position_size),
            'direction': 'LONG' if position_size > 0 else 'SHORT'
        }