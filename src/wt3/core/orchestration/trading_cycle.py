"""
Trading cycle execution for the WT3 Agent with Moonward integration.

This module handles the execution of individual trading cycles,
including signal retrieval, trade execution, and state updates.
"""

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ...__main__ import WT3Agent

logger = logging.getLogger(__name__)


async def trading_cycle(agent: 'WT3Agent'):
    """Execute a single trading cycle.
    
    This function:
    1. Gets the latest signal from the signal service
    2. Executes the trade if a decision is made
    3. Updates the trading state with the result
    
    Args:
        agent (WT3Agent): The trading agent instance
    """
    try:
        prediction = await agent.signal_client.get_prediction()
        if not prediction:
            logger.warning("No prediction received from signal service")
            agent.trading_state.add_activity("NONE", "no_signal", {})
            return
            
        logger.debug(f"Received prediction: {prediction}")
        
        trade_decision = prediction.get('trade_decision')
        if not trade_decision:
            logger.debug("No trade decision in signal - no action needed")
            agent.trading_state.add_activity("NONE", "no_action", {})
            return
        
        logger.info(f"Processing trade signal: {trade_decision.get('action')} for {trade_decision.get('coin')}")
        coin = trade_decision.get('coin', 'UNKNOWN')
        
        try:
            current_price = await agent.trading_tools.get_current_price(coin)
            position_size = await agent.trading_tools.get_position_size(coin)
            position_direction = "LONG" if position_size > 0 else "SHORT" if position_size < 0 else "NONE"
            
            position_value = abs(position_size) * current_price if position_size != 0 else 0
            
            entry_price = await agent.trading_tools.get_entry_price(coin) if position_size != 0 else None
            
            pnl_percent = None
            if position_size != 0 and entry_price:
                if position_direction == "LONG":
                    pnl_percent = (current_price - entry_price) / entry_price * 100
                else:
                    pnl_percent = (entry_price - current_price) / entry_price * 100
            
            market_data = {
                "current_price": current_price,
                "position_size": position_size,
                "position_direction": position_direction,
                "position_value": position_value
            }
            
            if entry_price:
                market_data["entry_price"] = entry_price
            if pnl_percent is not None:
                market_data["pnl_percent"] = pnl_percent
                
        except Exception as e:
            logger.warning(f"Could not retrieve market data for {coin}: {e}")
            market_data = {}
        
        signal_data = {}
        if "timestamp" in prediction:
            signal_data["signal_timestamp"] = prediction["timestamp"]
        
        activity_data = {**market_data, **signal_data}
        
        try:
            result = await agent.trading_tools.execute_trade_signal(prediction)
            logger.info(f"Trade execution result: {result}")
            
            action = trade_decision.get('action', 'unknown')
            
            trade_data = {
                'action_type': action
            }
            
            if isinstance(result, dict):
                if 'execution_price' in result:
                    trade_data['execution_price'] = result['execution_price']
                if 'fee' in result:
                    trade_data['fee'] = result['fee']
                if 'order_id' in result:
                    trade_data['order_id'] = result['order_id']
            
            combined_data = {**activity_data, **trade_data}
            
            if action == 'buy' or action == 'sell':
                agent.trading_state.add_activity(coin, "executed", combined_data)
            elif action == 'close':
                agent.trading_state.add_activity(coin, "closed", combined_data)
                
        except Exception as e:
            logger.error(f"Error executing trade: {e}")
            error_data = {**activity_data, 'error': str(e)}
            agent.trading_state.add_activity(coin, "failed", error_data)
            
    except Exception as e:
        logger.error(f"Error in trading cycle: {e}")
        agent.trading_state.add_activity("UNKNOWN", "error", {'error': str(e)})
