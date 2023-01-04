from datetime import datetime, timezone, timedelta
import io
from typing import Iterable

import aiohttp
from vkbottle.bot import Bot, Message
from vkbottle.dispatch.rules.base import CommandRule
from vkbottle import KeyboardButtonColor, Text, Keyboard
from vkbottle import PhotoMessageUploader, BaseStateGroup
from vkbottle_types.objects import PhotosPhoto
from PIL import Image

from config import TOKEN

bot = Bot(token=TOKEN)


MAIN_KEYBOARD = (
    Keyboard(one_time=False, inline=False)
    .add(Text("Изображения", payload={"keyboard": "images"}), color=KeyboardButtonColor.POSITIVE)
    .add(Text("Время", payload={"command": "time"}))
    .get_json()
)

IMAGES_KEYBOARD = (
  Keyboard(one_time=False, inline=False)
    .add(Text("Сделать чёрнобелым", payload={"command": "monochrome"}))
    .add(Text("Получить аватарку", payload={"command": "avatar"}))
    .row()
    .add(Text("Вернуться", payload={"keyboard": "main"}), color=KeyboardButtonColor.NEGATIVE)
    .get_json()
)


async def return_to_keyboard(message: Message, keyboard: str):
  await message.answer(message="Что дальше?",keyboard=keyboard)


@bot.on.message(payload={"keyboard": "main"})
async def redirect_to_main_keyboard(message: Message):
  await return_to_keyboard(message=message, keyboard=MAIN_KEYBOARD)


@bot.on.message(payload={"keyboard": "images"})
async def redirect_to_images_keyboard(message: Message):
  await return_to_keyboard(message=message, keyboard=IMAGES_KEYBOARD)


class ImageProcessingStates(BaseStateGroup):
  PROCESSING = 1
  COMPLETE = 0


@bot.on.private_message(func=lambda message: (
  message.text is not None 
  and any(variant in message.text.lower() for variant in ("привет", "начать", "помощь", "меню"))
))
async def on_start(message: Message):
  user = await message.get_user()
  
  await message.answer(f"Привет, {user.first_name}. Держи меню!", keyboard=MAIN_KEYBOARD)


@bot.on.message(CommandRule("time"))
@bot.on.message(payload={'command': 'time'})
async def on_time_request(message: Message):
  user = await message.get_user(fields="timezone")

  await message.answer(f"""Сейчас {datetime
                       .fromtimestamp(
                         message.date, 
                         tz=timezone(timedelta(hours=3))
                       )
                       .strftime("%H:%M:%S")} по Москве""")


@bot.on.message(CommandRule("avatar"))
@bot.on.message(payload={'command': 'avatar'})
async def on_get_avatar(message: Message):
  user = await message.get_user(fields="photo_id")
  
  if user.photo_id is None:
    await message.answer("У вас нет аватара")
    return
  
  await message.answer(attachment=f"photo{user.photo_id}")

@bot.on.message(state=ImageProcessingStates.PROCESSING)
async def on_process_images(message: Message, callback=None):
  photos = message.get_photo_attachments()
  
  if callback is None:
    callback = message.state_peer.payload['callback']
  
  if len(photos) > 0:
    async for attachment in callback(photos):
      await message.answer(attachment=attachment)
    await bot.state_dispenser.set(message.peer_id, ImageProcessingStates.COMPLETE, callback=None)
    await redirect_to_images_keyboard(message)
    return 
  
  await message.answer("Пришлите фотографии в своём следующем сообщении.")
  
  await bot.state_dispenser.set(message.peer_id, ImageProcessingStates.PROCESSING, callback=callback)

@bot.on.message(CommandRule("monochrome"))
@bot.on.message(payload={'command': 'monochrome'})
async def on_monochromize(message: Message):
  await on_process_images(message, load_monochromized)

async def load_monochromized(photos: Iterable[PhotosPhoto]):
  for photo in photos:    
    async with aiohttp.ClientSession() as session:
      response = await session.get(photo.sizes[5].url)
      image_bytes = await response.content.read()
    
    with io.BytesIO(image_bytes) as imageIO:
      imageIO.seek(0)
      image = Image.open(imageIO)
      image = image.convert("L")
    
    with io.BytesIO() as output:
      image.save(output, format="PNG")
      output.seek(0)
      attachment = await PhotoMessageUploader(bot.api).upload(output.read())
    
    image.close()
    yield attachment


if __name__ == "__main__":
  bot.run_forever()
