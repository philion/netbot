#!/usr/bin/env python3

import os
import re
import logging
import datetime as dt

import discord
import redmine
#import netbox

from discord.commands import option
from dotenv import load_dotenv

from discord.ext import commands

logging.basicConfig(level=logging.DEBUG, 
    format="{asctime} {levelname:<8s} {name:<16} {message}", style='{')

logging.getLogger("discord.gateway").setLevel(logging.WARNING)
logging.getLogger("discord.http").setLevel(logging.WARNING)

log = logging.getLogger(__name__)

log.info('initializing bot')

class NetBot(commands.Bot):
    def __init__(self, redmine: redmine.Client):
        log.info(f'initializing {self}')
        intents = discord.Intents.default()
        intents.message_content = True

        self.redmine = redmine

        super().__init__(
            command_prefix=commands.when_mentioned_or("!"), intents=intents
        )

    def run(self):
        log.info(f"starting {self}")
        super().run(os.getenv('DISCORD_TOKEN'))

    async def on_ready(self):
        log.info(f"Logged in as {self.user} (ID: {self.user.id})")

    async def on_thread_join(self, thread):
        await thread.join()
        log.info(f"Joined thread: {thread}")

    async def on_message(self, message: discord.Message):
        # Make sure we won't be replying to ourselves.
        #if message.author.id == bot.user.id:
        #    return
        if isinstance(message.channel, discord.Thread):
            # get the ticket id from the thread name
            ticket_id = bot.parse_thread_title(message.channel.name)
            if ticket_id:
                await self.sync_new_message(ticket_id, message)
            # else just a normal thread, do nothing
            
    async def sync_new_message(self, ticket_id:int, message: discord.Message):
        #ticket = redmine.get_ticket(ticket_id, include_journals=True)
        # create a note with translated discord user id with the update (or one big one?)
        # double-check that self.id <> author.id?
        user = self.redmine.find_discord_user(message.author.name)
        if user:
            client.append_message(ticket_id, user.login, message.content)
            log.debug(f"SYNCED: ticket={ticket_id}, user={user.login}, msg={message.content}")
        else:
            log.error("Unknown discord user: {message.author.name}, skipping message")

    async def synchronize_ticket(self, ticket, thread, ctx: discord.ApplicationContext):
        last_sync = self.redmine.get_field(ticket, "sync")
        
        # start of the process, will become "last update"
        timestamp = dt.datetime.utcnow().astimezone(dt.timezone.utc)

        notes = client.get_notes_since(ticket.id, last_sync)
        log.info(f"syncing {len(notes)} notes from {ticket.id} --> {thread}")

        for note in notes:
            msg = f"> **{note.user.name}** at *{note.created_on}*\n\n{note.notes}"
            await thread.send(msg)

        # query discord for updates to thread since last-update
        # see https://docs.pycord.dev/en/stable/api/models.html#discord.Thread.history
        async for message in thread.history(after=last_sync):
            # ignore bot messages!
            if message.author.id != bot.user.id:
                # for each, create a note with translated discord user id with the update (or one big one?)
                user = client.find_discord_user(message.author.name)
                if user:
                    log.debug(f"SYNC: ticket={ticket.id}, user={user.login}, msg={message.content}")
                    client.append_message(ticket.id, user.login, message.content)
                else:
                    log.error("Unknown discord user: {message.author.name}, skipping message")
        else:
            log.debug(f"No new discord messages found since {last_sync}")

        # update the SYNC timestamp
        client.update_syncdata(ticket.id, timestamp)
        log.info(f"completed sync for {ticket.id} <--> {thread}")

    def parse_thread_title(self, title:str) -> int:
        match = re.match(r'^Ticket #(\d+):', title)
        if match:
            return int(match.group(1))




log.info(f"initializing {__name__}")
load_dotenv()
#netbox_client = netbox.Client()
client = redmine.Client()
bot = NetBot(client)
# register cogs
bot.load_extension("cog_scn")
bot.load_extension("cog_tickets")

@bot.slash_command(name="new", description="Create a new ticket") 
@option("title", description="Title of the new SCN ticket")
@option("add_thread", description="Create a Discord thread for the new ticket", default=False)
async def create_new_ticket(ctx: discord.ApplicationContext, title:str, add_thread=False):
    user = client.find_discord_user(ctx.user.name)
    # text templating
    text = f"ticket created by Discord user {ctx.user.name} -> {user.login}, with the text: {title}"
    ticket = client.create_ticket(user.login, title, text)
    if ticket:
        if add_thread:
            # todo set thread flag in discord
            thread = await create_thread(ticket, ctx)
            await ctx.respond(f"Created thread: {thread}")

        await print_ticket(ticket, ctx)
    # error handling? exception? 

@bot.slash_command(name="disthread") 
@option("ticket_id", description="ID of tick to create thread for")
async def thread_ticket(ctx: discord.ApplicationContext, ticket_id:int):
    ticket = client.get_ticket(ticket_id)
    if ticket:
        # create the thread...
        thread = await create_thread(ticket, ctx)

        # update the discord flag on tickets, add a note with url of thread; thread.jump_url
        # TODO message templates
        note = f"Created Discord thread: {thread.name}: {thread.jump_url}"
        user = client.find_discord_user(ctx.user.name)
        client.enable_discord_sync(ticket.id, user.login, note)

        # sync the ticket, so everything is up to date
        await bot.synchronize_ticket(ticket.id, thread, ctx)

        # TODO format command for single ticket
        await ctx.respond(f"Created new thread for {ticket.id}: {thread}") # todo add some fancy formatting
    else:
        await ctx.respond(f"ERROR: Unkown ticket ID: {ticket_id}") # todo add some fancy formatting


async def create_thread(ticket, ctx):
    log.info(f"creating a new thread for ticket #{ticket.id} in channel: {ctx.channel}")
    name = f"Ticket #{ticket.id}: {ticket.subject[:20]}"
    return await ctx.channel.create_thread(name=name)

## refactor all this formatting stuff.

def format_section(tickets, status):
    section = ""
    section += f"> {status}\n"
    for ticket in tickets:
        if ticket.status.name == status:
            url = client.get_field(ticket, "url")
            assigned = client.get_field(ticket, "assigned")
            section += f"[**`{ticket.id:>4}`**]({url})`  {ticket.priority.name:<6}  {ticket.updated_on[:10]}\
                    {assigned[:20]:<20}  {ticket.subject}`\n"
    return section

def format_tickets(tickets, fields=["link","priority","updated","assigned","subject"]):
    if tickets is None:
        return "No tickets found."
    
    section = ""
    for ticket in tickets:
        section += format_ticket(ticket, fields) + "\n" # append each ticket
    return section.strip()

def format_ticket(ticket, fields):
    section = ""
    for field in fields:
        section += client.get_field(ticket, field) + " " # spacer, one space
    return section.strip() # remove trailing whitespace

async def print_tickets(tickets, ctx):
    msg = format_tickets(tickets)
    if len(msg) > 2000:
        log.warning("message over 2000 chars. truncing.")
        msg = msg[:2000]
    await ctx.respond(msg)

async def print_ticket(ticket, ctx):
    msg = format_ticket(ticket, fields=["link","priority","updated","assigned","subject"])

    if len(msg) > 2000:
        log.warning("message over 2000 chars. truncing.")
        msg = msg[:2000]
    await ctx.respond(msg)

# figure out what the term refers to
# better way? DRY
def resolve_query_term(term):
    # special cases: ticket num and team name
    try:
        id = int(term)
        ticket = client.get_ticket(id)
        return [ticket]
    except ValueError:
        # not a numeric id, check team
        if client.is_user_or_group(term):
            return client.tickets_for_team(term)
        else:
            # assume a search term
            return client.search_tickets(term)


#@bot.slash_command(name="tickets")
async def XXXtickets_command(ctx: discord.ApplicationContext, params: str):
    # different options: none, me (default), [group-name], intake, tracker name
    # buid index for trackers, groups
    # add groups to users.

    # lookup the user
    user = client.find_discord_user(ctx.user.name)
    log.info(f"found user mapping for {ctx.user.name}: {user}")

    args = params.split()
    #print(f"args={args}")

    if len(args) == 0 or args[0] == "me":
        await print_tickets(client.my_tickets(user.login), ctx)
    elif len(args) == 1:
        await print_tickets(resolve_query_term(args[0]), ctx)
    elif len(args) == 2:
        # unassign, progress, resolve
        try:
            id = int(args[0])
            action = args[1]

            if action not in ["unassign", "progress", "resolve"]:
                print(f"unknown operation: {action}")
                return

            match action:
                case "unassign":
                    client.unassign_ticket(id, user.login)
                    await print_ticket(client.get_ticket(id), ctx)
                case "resolve":
                    client.resolve_ticket(id, user.login)
                    await print_ticket(client.get_ticket(id), ctx)
                case "progress":
                    client.progress_ticket(id, user.login)
                    await print_ticket(client.get_ticket(id), ctx)
        except ValueError:
            print(f"invalid ticket number: {args[0]}")
            return
    elif len(args) == 3:
        try:
            id = int(args[0])
            action = args[1]
            target = args[2]

            if action != "assign":
                print(f"unknown operation: {action}")
                return

            client.assign_ticket(id, target)
            await print_ticket(client.get_ticket(id), ctx)
        except ValueError:
            print(f"invalid ticket number: {args[0]}")
            exit(1)
    else:
        print(f"invalid command: {args}")
        return

    
# run the bot
bot.run()
