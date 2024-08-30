"""
This cog will check the restauration page of the school website, and post the menu on Discord.
"""

from __future__ import annotations

import contextlib
import json
import logging
import re
from os import path
from typing import TYPE_CHECKING

import discord
import httpx
from bs4 import BeautifulSoup
from discord import HTTPException, TextChannel, app_commands
from discord.ext import tasks
from discord.ext.commands import Cog  # pyright: ignore[reportMissingTypeStubs]

if TYPE_CHECKING:
    from bot import FISABot

IMAGES_REGEX = re.compile(r"https://lycee-kleber.com.fr/wp-content/uploads/\d{4}/\d{2}/([^.]+).jpg")
RESTAURATION_PATH = "./data/restauration.json"

logger = logging.getLogger(__name__)


class Restauration(Cog):
    def __init__(self, bot: FISABot) -> None:
        self.bot = bot

        self.already_posted: list[str] = self.read_restauration_file()

    async def cog_load(self) -> None:
        self.check_menu.start()

    async def cog_unload(self) -> None:
        self.check_menu.stop()

    def add_restauration_file(self, filename: str) -> None:
        """A utility function to register what menu file has already been sent

        In a beautiful world, we should use a database such as sqlite3.
        Maybe I will improve this on day.. or could you ?
        Not an excessive work.

        Args:
            filename: the filename of the menu image
        """
        self.already_posted.append(filename)
        with open(RESTAURATION_PATH, "w") as f:
            json.dump(self.already_posted, f)

    def read_restauration_file(self) -> list[str]:
        """A utility function to get the list of what menu file has already been sent.

        Returns:
            The list of menu images filenames.
        """
        if not path.exists(RESTAURATION_PATH):
            with open(RESTAURATION_PATH, "w") as f:
                json.dump([], f)
            return []
        with open(RESTAURATION_PATH, "r") as f:
            return json.load(f)

    async def get_imgs(self) -> tuple[tuple[str, ...], tuple[str, ...]]:
        """Scrap the website to get the menu and allergenes images.

        Returns:
            A tuple with fr:MENUs, and a second tuple with fr:ALLERGENES.
        """
        async with httpx.AsyncClient() as client:
            result = await client.get("https://lycee-kleber.com.fr/restauration", follow_redirects=True)
            page = result.text

        scrap = BeautifulSoup(page, "html.parser")
        element = scrap.find_all("a", href=lambda r: bool(IMAGES_REGEX.match(r.text)))
        links: list[str] = [e.get("href") for e in element]

        menus: tuple[str, ...] = tuple(
            link for link in links if (m := IMAGES_REGEX.match(link)) and m.group(1).lower().startswith("menu")
        )
        allergenes: tuple[str, ...] = tuple(
            link for link in links if (m := IMAGES_REGEX.match(link)) and m.group(1).lower().startswith("allergenes")
        )
        return menus, allergenes

    @tasks.loop(minutes=60)
    async def check_menu(self) -> None:
        """Post the menu if there is a new one, checked every hour."""
        try:
            menus, _ = await self.get_imgs()
        except Exception:
            logger.exception("Getting the menu raised an unhandled exception.")
            return
        menus = [m for m in menus if m not in self.already_posted]  # filter with only new ones.

        if not menus:
            return
        for img_link in menus:
            self.add_restauration_file(img_link)

        channels: list[TextChannel] = [
            ch for ch in self.bot.get_all_channels() if isinstance(ch, TextChannel) and ch.name == "menu-cantine"
        ]

        for channel in channels:
            with contextlib.suppress(HTTPException):
                await channel.send("\n".join(menus))

    @app_commands.command(name="allergenes", description="Affiche les allergènes du menu du jour.")
    async def allergen(self, inter: discord.Interaction):
        _, allergens = await self.get_imgs()
        bn = "\n"
        await inter.response.send_message(
            "Voici les allergènes du menu du jour :\n"
            f"{bn.join(allergens)}"
            "\n\nS'ils ne sont pas à jour, c'est que le lycée ne les a pas publié.\n"
            "Attention : les allergènes sont susceptibles d'être modifiés, merci de se référer au panneau"
            " d'affichage à la restauration scolaire."
        )


async def setup(bot: FISABot):
    await bot.add_cog(Restauration(bot))
