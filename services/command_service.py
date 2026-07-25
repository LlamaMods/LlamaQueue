from sqlalchemy.orm import Session

from database.models import CommandMapping
from services.default_commands import DEFAULT_COMMANDS


class CommandService:
    def __init__(self, db: Session, user_id: int):
        self.db = db
        self.user_id = user_id

    def get_all(self):
        self.ensure_defaults()

        return (
            self.db.query(CommandMapping)
            .filter(CommandMapping.user_id == self.user_id)
            .order_by(CommandMapping.id)
            .all()
        )

    def get_sync_status(self, nightbot_commands):
        """
        Compare LlamaQueue commands against Nightbot commands.
        """

        llama_commands = self.get_all()

        nightbot_lookup = {
            command["name"].lower(): command
            for command in nightbot_commands
        }

        results = []

        for command in llama_commands:

            status = "missing"

            nightbot_command = nightbot_lookup.get(command.command.lower())
           
            if nightbot_command:
            
                status = "installed"
            
                if (
                    nightbot_command.get("message", "") != command.message
                     or nightbot_command.get("userLevel", "").lower() != command.permission.lower()
                     or int(nightbot_command.get("coolDown", 30)) != command.cooldown
                ):
                    status = "update"

            results.append(
                {
                    "mapping": command,
                    "status": status,
                    "nightbot": nightbot_command,
                }
            )

        return results

def ensure_defaults(self):

    existing = {
        mapping.action: mapping
        for mapping in (
            self.db.query(CommandMapping)
            .filter(CommandMapping.user_id == self.user_id)
            .all()
        )
    }

    changed = False

    for command in DEFAULT_COMMANDS:

        mapping = existing.get(command["action"])

        if mapping is None:
            self.db.add(
                CommandMapping(
                    user_id=self.user_id,
                    action=command["action"],
                    description=command["description"],
                    builtin=command["builtin"],
                    command=command["command"],
                    message=command["message"],
                    permission=command["permission"],
                    cooldown=command["cooldown"],
                    enabled=command.get("enabled", True),
                )
            )
            changed = True

        elif mapping.builtin:
            if (
                mapping.description != command["description"]
                or mapping.command != command["command"]
                or mapping.message != command["message"]
                or mapping.permission != command["permission"]
                or mapping.cooldown != command["cooldown"]
                or mapping.enabled != command.get("enabled", True)
            ):
                mapping.description = command["description"]
                mapping.command = command["command"]
                mapping.message = command["message"]
                mapping.permission = command["permission"]
                mapping.cooldown = command["cooldown"]
                mapping.enabled = command.get("enabled", True)
                changed = True

    if changed:
        self.db.commit()