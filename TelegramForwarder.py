import time
import datetime
import asyncio
from telethon.sync import TelegramClient
from telethon import errors

class TelegramForwarder:
    def __init__(self, api_id, api_hash, phone_number):
        self.api_id = api_id
        self.api_hash = api_hash
        self.phone_number = phone_number
        self.client = TelegramClient('session_' + phone_number, api_id, api_hash)
        self.active_tasks = []  # List to track active forwarding tasks
        self.last_forwarded_keywords = {}
        self.last_forwarded_solana = {}
        self.last_forwarded_ethereum = {}
        self.last_forwarded_cashtags = {}

    def _can_forward(self, message, message_type, timer):
        """
        Determines if the message can be forwarded based on the timer.
        """
        now = datetime.datetime.now()

        # Select the appropriate dictionary based on message type
        if message_type == "keywords":
            last_forwarded = self.last_forwarded_keywords.get(message)
        elif message_type == "solana":
            last_forwarded = self.last_forwarded_solana.get(message)
        elif message_type == "ethereum":
            last_forwarded = self.last_forwarded_ethereum.get(message)
        elif message_type == "cashtags":
            last_forwarded = self.last_forwarded_cashtags.get(message)
        else:
            return True

        # If this message has never been forwarded, allow it
        if not last_forwarded:
            return True

        # Calculate the time difference
        time_diff = now - last_forwarded
        return time_diff >= timer

    def _update_forward_time(self, message, message_type):
        """
        Updates the last forwarded time for the given message.
        """
        now = datetime.datetime.now()

        if message_type == "keywords":
            self.last_forwarded_keywords[message] = now
        elif message_type == "solana":
            self.last_forwarded_solana[message] = now
        elif message_type == "ethereum":
            self.last_forwarded_ethereum[message] = now
        elif message_type == "cashtags":
            self.last_forwarded_cashtags[message] = now

    async def list_chats(self):
        await self.client.connect()

        # Ensure you're authorized
        if not await self.client.is_user_authorized():
            await self.client.send_code_request(self.phone_number)
            await self.client.sign_in(self.phone_number, input('Enter the code: '))

        # Get a list of all the dialogs (chats)
        dialogs = await self.client.get_dialogs()
        chats_file = open(f"chats_of_{self.phone_number}.txt", "w", encoding='utf-8')
        # Print information about each chat
        for dialog in dialogs:
            username = getattr(dialog.entity, 'username', 'N/A') # Safely check for username attribute
            print(f"Chat ID: {dialog.id}, Title: {dialog.title}, Username: {username}")
            chats_file.write(f"Chat ID: {dialog.id}, Title: {dialog.title}, Username: {username} \n")

        chats_file.close()
        print("List of groups printed successfully!")

    async def _get_chat_id_from_title(self, title):
        """Helper method to get chat ID from title."""
        dialogs = await self.client.get_dialogs()
        for dialog in dialogs:
            if dialog.title.lower() == title.lower():
                return dialog.id
        raise ValueError(f"Chat with title '{title}' not found.")

    async def forward_messages_to_channel(self, source_chats, destinations, keywords, 
                                          solana_enabled=False, solana_source_chats=None, solana_destinations=None, solana_timer=None,
                                          eth_enabled=False, eth_source_chats=None, eth_destinations=None, eth_timer=None,
                                          cashtag_enabled=False, cashtag_source_chats=None, cashtag_destinations=None, cashtag_timer=None,
                                          keyword_timer=None):
        task = asyncio.current_task()  # Get the current task to track it
        self.active_tasks.append(task)  # Add the task to the active tasks list

        await self.client.connect()

        # Ensure you're authorized
        if not await self.client.is_user_authorized():
            await self.client.send_code_request(self.phone_number)
            await self.client.sign_in(self.phone_number, input('Enter the code: '))

        # Helper function to parse timers
        def parse_timer(timer_str):
            if "month" in timer_str:
                months = int(timer_str.split(" ")[0])
                return datetime.timedelta(days=months * 30)  # Approximate month as 30 days
            elif "day" in timer_str:
                days = int(timer_str.split(" ")[0])
                return datetime.timedelta(days=days)
            elif "minute" in timer_str:
                minutes = int(timer_str.split(" ")[0])
                return datetime.timedelta(minutes=minutes)
            elif "hour" in timer_str:
                hours = int(timer_str.split(" ")[0])
                return datetime.timedelta(hours=hours)
            return datetime.timedelta()  # Default to 0 if no valid time

        keyword_timer_delta = parse_timer(keyword_timer) if keyword_timer else datetime.timedelta()
        solana_timer_delta = parse_timer(solana_timer) if solana_timer else datetime.timedelta()
        eth_timer_delta = parse_timer(eth_timer) if eth_timer else datetime.timedelta()
        cashtag_timer_delta = parse_timer(cashtag_timer) if cashtag_timer else datetime.timedelta()

        # Forward keyword-based messages
        for source_chat in source_chats:
            if isinstance(source_chat, str) and source_chat.lstrip('-').isdigit():
                source_chat_id = int(source_chat)  # Convert it to an integer (chat ID)
            elif isinstance(source_chat, str):
                # It's a title, try to resolve it
                print(f"Finding chat by title: {source_chat}")
                try:
                    source_chat_id = await self._get_chat_id_from_title(source_chat)
                    print(f"Found chat ID for '{source_chat}': {source_chat_id}")
                except ValueError as e:
                    print(e)
                    continue  # Skip to the next source chat if this one fails
            else:
                source_chat_id = source_chat  # Use the provided chat ID (if it's already a number)

            last_message_id = (await self.client.get_messages(source_chat_id, limit=1))[0].id
            while True:
                # Check if this task is canceled
                if task.cancelled():
                    print("Forwarding job has been stopped.")
                    break

                messages = await self.client.get_messages(source_chat_id, min_id=last_message_id, limit=None)
                for message in reversed(messages):
                    if keywords and message.text and any(keyword in message.text.lower() for keyword in keywords):
                        if self._can_forward(message.text, "keywords", keyword_timer_delta):
                            for destination in destinations:
                                await self._send_message(destination, message.text, False)
                            self._update_forward_time(message.text, "keywords")
                    last_message_id = max(last_message_id, message.id)
                await asyncio.sleep(5)

        # Forward Solana contract messages
        if solana_enabled:
            for solana_source_chat in solana_source_chats:
                if isinstance(solana_source_chat, str) and solana_source_chat.lstrip('-').isdigit():
                    solana_source_chat_id = int(solana_source_chat)  # Convert it to an integer (chat ID)
                elif isinstance(solana_source_chat, str):
                    print(f"Finding chat by title: {solana_source_chat}")
                    try:
                        solana_source_chat_id = await self._get_chat_id_from_title(solana_source_chat)
                        print(f"Found chat ID for '{solana_source_chat}': {solana_source_chat_id}")
                    except ValueError as e:
                        print(e)
                        continue  # Skip to the next source chat if this one fails
                else:
                    solana_source_chat_id = solana_source_chat  # Use the provided chat ID (if it's already a number)

                last_message_id = (await self.client.get_messages(solana_source_chat_id, limit=1))[0].id
                while True:
                    if task.cancelled():
                        print("Solana forwarding job has been stopped.")
                        break

                    messages = await self.client.get_messages(solana_source_chat_id, min_id=last_message_id, limit=None)
                    for message in reversed(messages):
                        solana_contract = self._find_solana_contract(message.text)
                        if solana_contract and self._can_forward(solana_contract, "solana", solana_timer_delta):
                            for solana_destination in solana_destinations:
                                await self._send_message(solana_destination, solana_contract, False)
                            self._update_forward_time(solana_contract, "solana")
                    last_message_id = max(last_message_id, message.id)
                await asyncio.sleep(5)

        # Forward Ethereum contract messages
        if eth_enabled:
            for eth_source_chat in eth_source_chats:
                if isinstance(eth_source_chat, str) and eth_source_chat.lstrip('-').isdigit():
                    eth_source_chat_id = int(eth_source_chat)  # Convert it to an integer (chat ID)
                elif isinstance(eth_source_chat, str):
                    print(f"Finding chat by title: {eth_source_chat}")
                    try:
                        eth_source_chat_id = await self._get_chat_id_from_title(eth_source_chat)
                        print(f"Found chat ID for '{eth_source_chat}': {eth_source_chat_id}")
                    except ValueError as e:
                        print(e)
                        continue  # Skip to the next source chat if this one fails
                else:
                    eth_source_chat_id = eth_source_chat  # Use the provided chat ID (if it's already a number)

                last_message_id = (await self.client.get_messages(eth_source_chat_id, limit=1))[0].id
                while True:
                    if task.cancelled():
                        print("Ethereum forwarding job has been stopped.")
                        break

                    messages = await self.client.get_messages(eth_source_chat_id, min_id=last_message_id, limit=None)
                    for message in reversed(messages):
                        eth_contract = self._find_ethereum_contract(message.text)
                        if eth_contract and self._can_forward(eth_contract, "ethereum", eth_timer_delta):
                            for eth_destination in eth_destinations:
                                await self._send_message(eth_destination, eth_contract, False)
                            self._update_forward_time(eth_contract, "ethereum")
                    last_message_id = max(last_message_id, message.id)
                await asyncio.sleep(5)

        # Forward Cashtag messages
        if cashtag_enabled:
            for cashtag_source_chat in cashtag_source_chats:
                if isinstance(cashtag_source_chat, str) and cashtag_source_chat.lstrip('-').isdigit():
                    cashtag_source_chat_id = int(cashtag_source_chat)  # Convert it to an integer (chat ID)
                elif isinstance(cashtag_source_chat, str):
                    print(f"Finding chat by title: {cashtag_source_chat}")
                    try:
                        cashtag_source_chat_id = await self._get_chat_id_from_title(cashtag_source_chat)
                        print(f"Found chat ID for '{cashtag_source_chat}': {cashtag_source_chat_id}")
                    except ValueError as e:
                        print(e)
                        continue  # Skip to the next source chat if this one fails
                else:
                    cashtag_source_chat_id = cashtag_source_chat  # Use the provided chat ID (if it's already a number)

                last_message_id = (await self.client.get_messages(cashtag_source_chat_id, limit=1))[0].id
                while True:
                    if task.cancelled():
                        print("Cashtag forwarding job has been stopped.")
                        break

                    messages = await self.client.get_messages(cashtag_source_chat_id, min_id=last_message_id, limit=None)
                    for message in reversed(messages):
                        cashtags = self._find_cashtag(message.text)
                        if cashtags:
                            for cashtag in cashtags:
                                if self._can_forward(cashtag, "cashtags", cashtag_timer_delta):
                                    for cashtag_destination in cashtag_destinations:
                                        await self._send_message(cashtag_destination, cashtag, False)
                                    self._update_forward_time(cashtag, "cashtags")
                    last_message_id = max(last_message_id, message.id)
                await asyncio.sleep(5)

        # Remove this task from active tasks when done
        self.active_tasks.remove(task)  # Remove the task from the active tasks list


    async def _send_message(self, destination, message_text, is_bot):
        """Helper method to handle sending a message to a bot or a regular destination."""
        try:
            # Send the message to the bot or regular channel
            if is_bot:
                await self.client.send_message(destination, message_text)
                print(f"Message forwarded to bot {destination}: {message_text}")
            else:
                await self.client.send_message(destination, message_text)
                print(f"Message forwarded to channel/chat ID {destination}: {message_text}")
        except errors.FloodWaitError as e:
            print(f"Flood wait: Need to wait for {e.seconds} seconds")
            await asyncio.sleep(e.seconds)
        except Exception as e:
            print(f"An error occurred while forwarding the message: {e}")

    async def stop_forwarding_job(self, job_number):
        """Stops the specified forwarding job."""
        try:
            task = self.active_tasks[job_number]
            task.cancel()  # Cancel the task
            print(f"Forwarding job {job_number + 1} has been stopped.")
        except IndexError:
            print("Invalid job number. Please try again.")

def _find_solana_contract(self, text):
    import re
    solana_pattern = r'[1-9A-HJ-NP-Za-km-z]{32,44}'  # Base58 regex for Solana contract address
    matches = re.findall(solana_pattern, text)
    # Add custom validation logic if needed
    return matches[0] if matches else None

def _find_ethereum_contract(self, text):
    import re
    eth_pattern = r'0x[a-fA-F0-9]{40}'  # Regex for Ethereum contract address
    matches = re.findall(eth_pattern, text)
    # Add custom validation logic if needed
    return matches[0] if matches else None


# Function to read credentials from file
def read_credentials():
    try:
        with open("credentials.txt", "r") as file:
            lines = file.readlines()
            api_id = lines[0].strip()
            api_hash = lines[1].strip()
            phone_number = lines[2].strip()
            return api_id, api_hash, phone_number
    except FileNotFoundError:
        print("Credentials file not found.")
        return None, None, None

# Function to write credentials to file
def write_credentials(api_id, api_hash, phone_number):
    with open("credentials.txt", "w") as file:
        file.write(api_id + "\n")
        file.write(api_hash + "\n")
        file.write(phone_number + "\n")

async def main():
    # Attempt to read credentials from file
    api_id, api_hash, phone_number = read_credentials()
    
    if api_id is None or api_hash is None or phone_number is None:
        api_id = input("Enter your API ID: ")
        api_hash = input("Enter your API Hash: ")
        phone_number = input("Enter your phone number: ")
        write_credentials(api_id, api_hash, phone_number)

    forwarder = TelegramForwarder(api_id, api_hash, phone_number)

    while True:
        print("Choose an option:")
        print("1. List Chats")
        print("2. Forward Messages")
        print("3. Stop Forwarding")
        print("4. Exit")

        choice = input("Enter your choice: ")

        if choice == "1":
            await forwarder.list_chats()
            input("Press any key to return to the main menu...")
        elif choice == "2":
            # Show message types that the user can configure for forwarding
            print("\nChoose message types to forward:")
            print("1. Keywords")
            print("2. Solana Contracts")
            print("3. Ethereum Contracts")
            print("4. Cashtags")
            print("m. Return to Main Menu")

            selected_message_types = input("Enter the numbers of the message types you want to forward (comma separated): ").split(",")
            selected_message_types = [item.strip() for item in selected_message_types if item.strip()]

            # Start gathering configurations based on selected message types
            # -------------------------------------------------------------
            # Keywords Configuration
            source_chats, destinations, keywords, keyword_timer = None, None, None, None
            if '1' in selected_message_types:
                source_chats = input("Enter the source chats for keywords (comma separated IDs or titles): ").split(",")
                destinations = input("Enter the destinations for keywords (comma separated IDs or titles): ").split(",")
                keywords = input("Enter keywords to forward messages with specific keywords (comma separated), or leave blank to forward every message: ").split(",")
                keywords = [keyword.strip() for keyword in keywords if keyword.strip()]  # Clean keywords
                keyword_timer = input("Enter the timer for keywords (e.g., '10 minutes', '2 months'), or leave blank for no timer: ")

            # Solana Contracts Configuration
            solana_source_chats, solana_destinations, solana_timer = None, None, None
            solana_enabled = '2' in selected_message_types
            if solana_enabled:
                solana_source_chats = input("Enter the Solana source chats (comma separated): ").split(",")
                solana_destinations = input("Enter the Solana contract destinations (comma separated): ").split(",")
                solana_timer = input("Enter the timer for Solana contracts (e.g., '10 minutes', '2 months'), or leave blank for no timer: ")

            # Ethereum Contracts Configuration
            eth_source_chats, eth_destinations, eth_timer = None, None, None
            eth_enabled = '3' in selected_message_types
            if eth_enabled:
                eth_source_chats = input("Enter the Ethereum source chats (comma separated): ").split(",")
                eth_destinations = input("Enter the Ethereum contract destinations (comma separated): ").split(",")
                eth_timer = input("Enter the timer for Ethereum contracts (e.g., '10 minutes', '2 months'), or leave blank for no timer: ")

            # Cashtag Configuration
            cashtag_source_chats, cashtag_destinations, cashtag_timer = None, None, None
            cashtag_enabled = '4' in selected_message_types
            if cashtag_enabled:
                cashtag_source_chats = input("Enter the Cashtag source chats (comma separated): ").split(",")
                cashtag_destinations = input("Enter the Cashtag destinations (comma separated): ").split(",")
                cashtag_timer = input("Enter the timer for Cashtags (e.g., '10 minutes', '2 months'), or leave blank for no timer: ")

            print("Forwarding job initiated with the following settings:")
            if '1' in selected_message_types:
                print(f"Keywords: {keywords}, Source Chats: {source_chats}, Destinations: {destinations}, Timer: {keyword_timer}")
            if solana_enabled:
                print(f"Solana Source Chats: {solana_source_chats}, Destinations: {solana_destinations}, Timer: {solana_timer}")
            if eth_enabled:
                print(f"Ethereum Source Chats: {eth_source_chats}, Destinations: {eth_destinations}, Timer: {eth_timer}")
            if cashtag_enabled:
                print(f"Cashtag Source Chats: {cashtag_source_chats}, Destinations: {cashtag_destinations}, Timer: {cashtag_timer}")

            # Prepare tasks for concurrent execution of forwarding jobs
            tasks = []

            # Keywords Forwarding Job
            if '1' in selected_message_types:
                tasks.append(forwarder.forward_messages_to_channel(
                    source_chats=source_chats,
                    destinations=destinations,
                    keywords=keywords,
                    keyword_timer=keyword_timer
                ))

            # Solana Forwarding Job
            if solana_enabled:
                tasks.append(forwarder.forward_messages_to_channel(
                    solana_enabled=True,
                    solana_source_chats=solana_source_chats,
                    solana_destinations=solana_destinations,
                    solana_timer=solana_timer
                ))

            # Ethereum Forwarding Job
            if eth_enabled:
                tasks.append(forwarder.forward_messages_to_channel(
                    eth_enabled=True,
                    eth_source_chats=eth_source_chats,
                    eth_destinations=eth_destinations,
                    eth_timer=eth_timer
                ))

            # Cashtag Forwarding Job
            if cashtag_enabled:
                tasks.append(forwarder.forward_messages_to_channel(
                    cashtag_enabled=True,
                    cashtag_source_chats=cashtag_source_chats,
                    cashtag_destinations=cashtag_destinations,
                    cashtag_timer=cashtag_timer
                ))

            # Await all tasks concurrently
            if tasks:  # Check if there are tasks to run
                print("Jobs are now running...")
                for task in asyncio.as_completed(tasks):
                    await task  # Wait for each task to complete
                    # After each task, check if the user wants to return to the main menu
                    user_input = input("Type 'm' to return to the main menu or any other key to continue: ").strip().lower()
                    if user_input == 'm':
                        print("Returning to the main menu...")
                        break  # Exit the loop to return to the main menu

        elif choice == "3":
            # Stop Forwarding Jobs
            if not forwarder.active_tasks:
                print("No active forwarding jobs to stop.")
                input("Press any key to return to the main menu...")
                continue

            print("Currently running jobs:")
            for idx, task in enumerate(forwarder.active_tasks):
                print(f"{idx + 1}. Job {idx + 1}")  # Simple representation of job number

            job_number = input("Enter the number of the job you want to stop: ")
            if job_number.isdigit():
                job_number = int(job_number) - 1  # Convert to zero-based index
                await forwarder.stop_forwarding_job(job_number)

            input("Press any key to return to the main menu...")

        elif choice == "4":
            print("Exiting the application.")
            break  # Exit the while loop
        else:
            print("Invalid choice")
            input("Press any key to return to the main menu...")

# Start the event loop and run the main function
if __name__ == "__main__":
    asyncio.run(main())
