from contextlib import asynccontextmanager
from distutils.command.install_egg_info import safe_name
from fastapi import FastAPI
from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
import db_helper
import generic_helper

app = FastAPI()

inprogress_orders = {}

templates = Jinja2Templates(directory="templates")

@app.get('/')
def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post('/')
async def handle_request(request:Request):
    payload = await request.json()
    intent = payload['queryResult']['intent']['displayName']
    parameters = payload['queryResult']['parameters']
    ouput_contexts = payload['queryResult']['outputContexts']
    session_id = generic_helper.extract_session_id(ouput_contexts[0]['name'])
    
    intent_handler_dict = {
        
        'order.add - context: ongoing-order' : add_to_order,
        'order.remove - context: ongoing-order': remove_from_order,
        'order.complete - context:ongoing-order':complete_order,
        'track.order - context: ongoing-tracking': track_order
        
    }
    
    return intent_handler_dict[intent](parameters,session_id)
    
    # if intent == 'track.order - context: ongoing-tracking':
    #     return track_order(parameters)

def add_to_order(parameters:dict, session_id:str):
    food_items = parameters['food-item']
    quantities = parameters['number']
    
    if len(food_items) != len(quantities):
        fulfillment_text = 'Sorry, please specify the quantities of each food item.'
    else:
        new_food_dict = dict(zip(food_items, quantities))
        
        # Initialize current_food_dict here to ensure it's always defined
        current_food_dict = inprogress_orders.get(session_id, {})
        
        # Update the current_food_dict with new_food_dict
        current_food_dict.update(new_food_dict)
        
        # Save the updated current_food_dict back to inprogress_orders
        inprogress_orders[session_id] = current_food_dict
        
        order_str = generic_helper.get_str_from_food_dict(inprogress_orders[session_id])
        fulfillment_text = f'So far, you have: {order_str}. Do you want anything else?'
        
    return JSONResponse(content={'fulfillmentText': fulfillment_text})

def complete_order(parameters:dict,session_id:str):
    if session_id not in inprogress_orders:
        fulfillment_text = 'I am having a trouble finding your order. Please place a new order'
    else:
        order = inprogress_orders[session_id]
        order_id = save_to_db(order)
        
        if order_id == -1:
            fulfillment_text = 'sorry I could not process your order due to backend error, try again '
        else:
            order_total = db_helper.get_total_order_price(order_id)
            fulfillment_text= f'awesome! your order id is {order_id} and your order total is {order_total}. You can pay it at a time of delivery '
        
        del inprogress_orders[session_id]
        
    return JSONResponse(content={
        "fulfillmentText": fulfillment_text
    })    
        
def save_to_db(order:dict):
    next_order_id = db_helper.get_next_order_id()
    
    for food_item,quantity in order.items():
        rcode = db_helper.insert_order_item(
            food_item,
            quantity,
            next_order_id
        )
        
        if rcode == -1:
            return -1
        
    db_helper.insert_order_tracking(next_order_id,'in progress')    
    return next_order_id


def remove_from_order(parameters: dict, session_id: str):
    if session_id not in inprogress_orders:
        return JSONResponse(content={
            "fulfillmentText": "I'm having a trouble finding your order. Sorry! Can you place a new order please?"
        })
    
    food_items = parameters["food-item"]
    current_order = inprogress_orders[session_id]

    removed_items = []
    no_such_items = []

    for item in food_items:
        if item not in current_order:
            no_such_items.append(item)
        else:
            removed_items.append(item)
            del current_order[item]

    if len(removed_items) > 0:
        fulfillment_text = f'Removed {",".join(removed_items)} from your order!'

    if len(no_such_items) > 0:
        fulfillment_text = f' Your current order does not have {",".join(no_such_items)}'

    if len(current_order.keys()) == 0:
        fulfillment_text += " Your order is empty!"
    else:
        order_str = generic_helper.get_str_from_food_dict(current_order)
        fulfillment_text += f" Here is what is left in your order: {order_str}"

    return JSONResponse(content={
        "fulfillmentText": fulfillment_text
    })

    
               
         
def track_order(parameters: dict, session_id: str):
    order_id = parameters['number']
    order_status = db_helper.get_order_status(order_id)
    
    if order_status:
        fulfillment_text = f'The order status for order id:{order_id} is:{order_status}'
    else:
        fulfillment_text=f'No order found with order id: {order_id}'
    
    
    return JSONResponse(content={
            'fulfillmentText' : fulfillment_text
    })
    
    
    