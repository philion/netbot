#!/usr/bin/env python3

import sys
import logging
import humanize
import datetime as dt

import hashlib

from dotenv import load_dotenv

import redmine

# using https://pypi.org/project/rich/ for terminal formatting
from rich.console import Console
from rich.table import Table
from rich import box


#logging.basicConfig(level=logging.DEBUG)
log = logging.getLogger(__name__)


class CLI():
    def __init__(self):
        # load creds into env, and init the redmine client
        load_dotenv()
        self.client = redmine.Client()

    # figure out what the term refers to
    # better way?
    def resolve_query_term(self, term):
        # special cases: ticket num and team name
        try:
            id = int(term)
            ticket = self.client.get_ticket(id)
            return [ticket]
        except ValueError:
            # not a numeric id, check team
            if self.client.is_user_or_group(term):
                return self.client.tickets_for_team(term)
            else:
                # assume a search term
                return self.client.search_tickets(term)

    # the 'rich' version
    def print_tickets(self, tickets, fields=["link","status","priority","age","assigned","subject"]):
        if not tickets:
            print("no tickets found")
            return
        elif len(tickets) == 1:
            self.print_ticket(tickets[0])
            return

        console = Console()

        table = Table(show_header=True, box=box.SIMPLE_HEAD, collapse_padding=True, header_style="bold magenta")
        for field in fields:
            #table.add_column("Date", style="dim", width=12)
            table.add_column(field)

        for ticket in tickets:
            row = []
            for field in fields:
                row.append(self.get_formatted_field(ticket, field))
            table.add_row(*row)

        console.print(table)

    def get_formatted_field(self, ticket, field):
        value = self.client.get_field(ticket, field)

        priority_colors = {
            "Low": "dim",
            "Normal": "green",
            "High": "yellow",
            "Urgent": "orange",
            "Immediate": "red",
        }
	
        status_colors = {
            "New": "hot_pink",
            "In Progress": "green",
            "Feedback": "yellow",
            "Resolved": "dark_green",
            "Closed": "dim",
            "Rejected/Spam": "dim",
        }
        match field:
            case "link":
                url = self.client.get_field(ticket, "url")
                return f"[link={url}]{ticket.id}[/link]"
            case "subject":
                url = self.client.get_field(ticket, "url")
                return f"[link={url}]{value}[/link]"
            case "url":
                url = self.client.get_field(ticket, "url")
                return f"[link={url}]{value}[/link]"
            case "priority":
                if value in priority_colors:
                    color = priority_colors[value]
                    return f"[{color}]{value}[/{color}]"
            case "age":
                updated = dt.datetime.fromisoformat(ticket.updated_on)
                age = dt.datetime.now(dt.timezone.utc) - updated
                age_str = humanize.naturaldelta(age)

                color = None
                if age.days == 0:
                    color = "green"
                elif age.days > 0 and age.days <= 2:
                    pass # no color
                elif age.days > 2 and age.days <= 7:
                    color = "bright_yellow"
                elif age.days > 7 and age.days <= 15:
                    color = "dark_orange"
                else:
                    color = "red"
                if color:
                    return f"[{color}]{age_str}[/{color}]"
                else:
                    return age_str
            case "status":
                if value in status_colors:
                    color = status_colors[value]
                    return f"[{color}]{value}[/{color}]"
            case "assigned":
                # consistently-hash the value into a color
                # hash_val = hash(value) <-- this does it inconsistantly (for security reasons)
                hash_val = int(hashlib.md5(value.encode('utf-8')).hexdigest(), 16)
                r = (hash_val & 0xFF0000) >> 16;
                g = (hash_val & 0x00FF00) >> 8;
                b = hash_val & 0x0000FF;
                #print(f"val={value}: {hash_val} - {r},{g},{b}")
                return f"[rgb({r},{g},{b})]{value}[/rgb({r},{g},{b})]"
        return value

    
    def print_ticket(self, ticket):
        # print details for a single ticket
        console = Console()

        for name, value in ticket.__dict__.items():
            console.print(f"[dim]{name}:[/dim] [bold]{value}[/bold]")


def format_tickets(tickets, fields=["link","priority","updated","assigned","subject"]):
        if len(tickets) == 1:
            format_ticket_details(ticket[0])
        else:
            for ticket in tickets:
                print(format_ticket(ticket, fields))

def format_ticket(ticket, fields=["link","priority","updated","assigned", "subject"]):
    url = f"FIXME/issues/{ticket.id}"
    try: # hack to get around missing key
        assigned_to = ticket.assigned_to.name
    except AttributeError:
        assigned_to = ""

    section = ""
    for field in fields:
        match field:
            case "id":
                section += f"{ticket.id}"
            case "url":
                section += url
            case "link":
                section += f"[{ticket.id}]({url})"
            case "priority":
                section += f"{ticket.priority.name}"
            case "updated":
                section += f"{ticket.updated_on[:10]}" # just the date, strip time
            case "assigned":
                section += f"{assigned_to}"
            case "status":
                section += f"{ticket.status.name}"
            case "subject":
                section += f"{ticket.subject}"
        section += " " # spacer, one space
    return section.strip() # remove trailing whitespace
pass

def format_ticket_details(ticket):
    print(ticket)
    pass

def main():
    cli = CLI()
    
    # parse args
    args = sys.argv
    if len(args) == 1:
        cli.print_tickets(cli.client.my_tickets())
    elif len(args) == 2:
        cli.print_tickets(cli.resolve_query_term(args[1]))
    elif len(args) == 3:
        # unassign and resolve
        try:
            id = int(args[1])
            action = args[2]

            if action not in ["unassign", "resolve"]:
                print(f"unknown operation: {action}")
                exit(1)

            match action:
                case "unassign":
                    cli.client.unassign_ticket(id)
                case "resolve":
                    cli.client.resolve_ticket(id)
        except ValueError:
            print(f"invalid ticket number: {args[1]}")
            exit(1)
    elif len(args) == 4:
        try:
            id = int(args[1])
            action = args[2]
            target = args[3]

            if action not in ["assign", "progress"]:
                print(f"unknown operation: {action}")
                exit(1)

            match action:
                case "assign":
                    cli.client.assign_ticket(id, target)
                case "progress":
                    cli.client.progress_ticket(id, target)

        except ValueError:
            print(f"invalid ticket number: {args[1]}")
            exit(1)
    else:
        print("invalid command: {args}")
        exit(1)


if __name__ == '__main__':
    main()
