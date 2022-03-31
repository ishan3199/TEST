import logging
import asyncio
import uvicorn
from enums import OcppMisc as oc
from ocpp.routing import on
from ocpp.v16 import ChargePoint as cp
from ocpp.v16.enums import Action, RegistrationStatus, AuthorizationStatus, ResetType, ResetStatus
from ocpp.v16 import call_result, call
import os
import sys
from datetime import datetime
from fastapi import Body, FastAPI, status, Request, WebSocket, Depends
from chargepoint import ChargePoint



app = FastAPI()
#print(asgiref.__version__)
logging.basicConfig(level=logging.INFO)




class ChargePoint(cp):

    @on(Action.Heartbeat)
    async def on_HB(self):
        print("heart beat received from chargepoint")
        return call_result.HeartbeatPayload(current_time=datetime.utcnow().isoformat())

    @on(Action.Authorize)
    async def on_auth(self, id_tag, **kwargs):
        if id_tag == "test_cp2" or id_tag == "test_cp5":
            print("authorized")
            return call_result.AuthorizePayload(
                id_tag_info={oc.status.value: AuthorizationStatus.accepted.value}
            )
        else:
            print("Not Authorized")
            return call_result.AuthorizePayload(
                id_tag_info={oc.status.value: AuthorizationStatus.invalid.value}
            )


    @on(Action.BootNotification)
    def on_boot_notification(self, charge_point_vendor, charge_point_model, **kwargs):
        return call_result.BootNotificationPayload(
            current_time=datetime.utcnow().isoformat(),
            interval=1000,
            status=RegistrationStatus.accepted
        )


    async def reset(self, type: ResetType):

        return await self.call(call.ResetPayload( type=type))


    
    
class CentralSystem:
    def __init__(self):
        self._chargers = {}

    def register_charger(self, cp: ChargePoint):
        queue = asyncio.Queue(maxsize=1)
        task = asyncio.create_task(self.start_charger(cp, queue))
        self._chargers[cp] = task
        print(self._chargers)
        return queue

    async def start_charger(self, cp, queue):
        try:
            await cp.start()
        except Exception as error:
            print(f"Charger {cp.id} disconnected: {error}")
        finally:
            del self._chargers[cp]
            await queue.put(True)

    async def reset_fun(self, cp_id: str, rst_type: str):
        print("atleast got here")
        print(self._chargers.items())      # NO CHARGERS STORED HERE IDK WHY
        for cp, task in self._chargers.items():
            print(cp.id)
            if cp.id == cp_id:
                print("reached here")
                await cp.reset(rst_type)


class SocketAdapter:
    def __init__(self, websocket: WebSocket):
        self._ws = websocket

    async def recv(self) -> str:
        return await self._ws.receive_text()

    async def send(self, msg) -> str:
        await self._ws.send_text(msg)


        
@app.websocket("/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str, csms: CentralSystem = Depends(CentralSystem)):
    await websocket.accept(subprotocol='ocpp1.6')
    cp_id = websocket.url.path.strip('/')
    cp = ChargePoint(cp_id, SocketAdapter(websocket))
    print(f"charger {cp.id} connected.")

    queue = csms.register_charger(cp)
    await queue.get()



    

@app.post("/reset")
async def reset(request: Request, cms: CentralSystem = Depends(CentralSystem)):
    data = await request.json()
    print(f"API DATA to confirm {data}")
    get_response = await cms.reset_fun(data["cp_id"], data["type"])
    print(f"==> The response from charger==> {get_response}")
    return "sucess"



if __name__ == '__main__':
    uvicorn.run(app, host='0.0.0.0', port=2510)
