"""
This is a module that checks if some Twitch streamer is live.
"""
import asyncio
import json
import discord
from discord import app_commands
from discord.ext import commands, tasks
from source.settings import CONFIGS_DIRECTORY
from modules.TwitchNotifs.fetcher import check_live


class TwitchNotifsModule(commands.Cog):
    """
    This is an example module
    """

    def __init__(self, client: commands.Bot) -> None:
        self.client = client

        self.config_path: str = f"{CONFIGS_DIRECTORY}/twitchnotifs.json"
        self.module_config: dict[str, int] | None = None
        self.guild_config: list[dict[str, str | int | list]] | None = None

        self.channels_live: dict[str, bool] = dict()
        self.channels_init: bool = False

        self.load_configs()
        self.check.start()

    def load_configs(self) -> None:
        """
        Loads 'twitchnotifs.json' config file
        """

        with open(self.config_path, "r", encoding="utf-8") as file:
            config = json.loads(file.read())
            self.module_config = config["config"]
            self.guild_config = config["guild_config"]

        self.check.change_interval(seconds=self.module_config["update_interval"])

    async def fetch_channel_states(self) -> dict[str, bool]:
        """
        Checks all channels for their current state (live / offline)
        :return: 'name': True/False
        """

        # fetch all channels
        channels = set()
        for guild_config in self.guild_config:
            channels.update(guild_config["channels"])

        # limit concurrency
        sem = asyncio.Semaphore(self.module_config["threads"])

        # checking coroutine
        async def check_coro(channel_name):
            async with sem:
                return await check_live(channel_name)

        response = await asyncio.gather(
            *[check_coro(channel) for channel in channels])

        # zip 'channel': 'isLive?' together & return
        return {name: live for name, live in zip(channels, response)}

    @tasks.loop(minutes=1)
    async def check(self) -> None:
        """
        Check every 'update_interval' for a new stream
        """

        # check if we initialized current state of channels
        if not self.channels_init:
            self.channels_init = True
            self.channels_live = await self.fetch_channel_states()
            return

        # fetch current state
        new_channels_live = await self.fetch_channel_states()

        # go through all guilds
        for guild_config in self.guild_config:
            notification_channel = self.client.get_channel(guild_config["notifications_channel_id"])
            notification_format = guild_config["format"]
            role_ping = f"<@&{guild_config["role_id"]}>"

            # check every configured twitch channel
            for channel in guild_config["channels"]:
                # if a channel is live, and it wasn't before -> make a notification
                if new_channels_live[channel] != self.channels_live[channel] and new_channels_live[channel] is True:
                    msg = notification_format.format(
                        role_mention=role_ping,
                        channel_name=channel,  # so convenient, thx twitch
                        stream_url=f"https://www.twitch.tv/{channel}")
                    await notification_channel.send(msg)

        # update channel states
        self.channels_live = new_channels_live


async def setup(client: commands.Bot) -> None:
    await client.add_cog(TwitchNotifsModule(client))