import uvicorn
from fastapi import FastAPI
from NotificationItem import NotificationItem

app = FastAPI()

@app.post('/taskmaster')
def webhook(notif: NotificationItem):
    print(notif.model_dump(mode='json'))

def main():
    uvicorn.run("webhook:app", host="127.0.0.1", port=8000, reload=True)

if __name__ == '__main__':
    main()
