from yandex_music import Client
import time

client = Client()

# 1) Запрашиваем код устройства
dc = client.request_device_code()
print("Открой:", dc.verification_url)
print("Код:", dc.user_code)
print("Ждём подтверждения...")

# 2) Периодически опрашиваем, пока не выдадут токен
while True:
    token = client.poll_device_token(dc.device_code)
    if token and getattr(token, "access_token", None):
        print("YANDEX_MUSIC_TOKEN =", token.access_token)
        break
    time.sleep(getattr(dc, "interval", 5))