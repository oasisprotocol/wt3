"""
Trading cycle execution for the WT3 Agent.

This module handles the execution of individual trading cycles,
including signal retrieval, trade execution, and state updates.
"""

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ...__main__ import WT3Agent

logger = logging.getLogger(__name__)


async def trading_cycle(agent: 'WT3Agent', coin: str):
    """Execute a single trading cycle.
    
    This function:
    1. Gets the latest signal from the signal service
    2. Executes the trade if a decision is made
    3. Updates the trading state with the result
    
    Args:
        agent (WT3Agent): The trading agent instance
        coin (str): The trading pair symbol
    """
    try:
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
            logger.warning(f"Could not retrieve all market data: {e}")
            market_data = {}
        
        prediction = await agent.signal_client.get_prediction(coin)
        if not prediction:
            logger.warning("No prediction received from signal service")
            agent.trading_state.add_activity(coin, "no_signal", market_data)
            return
            
        logger.info(f"Received prediction: {prediction}")
        
        signal_data = {}
        if "timestamp" in prediction:
            signal_data["signal_timestamp"] = prediction["timestamp"]
        
        if "current_position" in prediction and prediction["current_position"]:
            position_info = prediction["current_position"]
            signal_data.update({
                "position_size_from_signal": position_info["size"],
                "position_direction_from_signal": position_info["direction"]
            })
            if "entry_price" in position_info:
                signal_data["entry_price_from_signal"] = position_info["entry_price"]
            logger.info(f"Current position from signal: {position_info['direction']} {position_info['size']} {coin}")
        
        activity_data = {**market_data, **signal_data}
        
        trade_decision = prediction.get('trade_decision')
        if not trade_decision:
            signal_position_direction = signal_data.get("position_direction_from_signal")
            
            if signal_position_direction:
                logger.info(f"No trade decision in signal - holding current {signal_position_direction} position (from signal)")
                hold_data = {**activity_data, 'direction': signal_position_direction}
                agent.trading_state.add_activity(coin, "hold", hold_data)
            elif position_size != 0:
                logger.info(f"No trade decision in signal - holding current {position_direction} position")
                hold_data = {**activity_data, 'direction': position_direction}
                agent.trading_state.add_activity(coin, "hold", hold_data)
            else:
                logger.info("No trade decision in signal - no action needed")
                agent.trading_state.add_activity(coin, "no_action", activity_data)
            return
            
        try:
            result = await agent.trading_tools.execute_trade_signal(prediction)
            logger.info(f"Trade execution result: {result}")
            
            action = trade_decision.get('action', 'unknown')
            direction = trade_decision.get('direction', 'unknown')
            confidence = trade_decision.get('confidence', 0.0)
            
            trade_data = {
                'direction': direction,
                'confidence': confidence,
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
            
            if action == 'open':
                agent.trading_state.add_activity(coin, "executed", combined_data)
            elif action == 'close':
                agent.trading_state.add_activity(coin, "closed", combined_data)
            elif action == 'close_and_reverse':
                agent.trading_state.add_activity(coin, "reversed", combined_data)
                
        except Exception as e:
            logger.error(f"Error executing trade: {e}")
            error_data = {**activity_data, 'error': str(e)}
            agent.trading_state.add_activity(coin, "failed", error_data)
            
    except Exception as e:
        logger.error(f"Error in trading cycle: {e}")
        agent.trading_state.add_activity(coin, "error", {'error': str(e)})