#!/usr/bin/env python3
import asyncio
import aiohttp
import random
import string
import datetime
import signal
import platform
from typing import List, Set
import argparse

class EmojiClient:
    def __init__(self, server_url: str, client_id: str):
        self.server_url = server_url
        self.client_id = client_id
        self.running = True
        self.emoji_types = ['😊', '😀', '😃', '😄', '😁', '😆', '😅', '😂', '🤣']
        
    async def send_emoji(self, session: aiohttp.ClientSession) -> int:
        """Send a random emoji for this client to the emoji service."""
        data = {
            "user_id": self.client_id,
            "emoji_type": random.choice(self.emoji_types),
            "timestamp": datetime.datetime.now().isoformat(),
            "client_id": self.client_id
        }
        
        try:
            async with session.post(f'{self.server_url}/emoji', json=data) as response:
                return response.status
        except aiohttp.ClientError as e:
            print(f"Error sending emoji for client {self.client_id}: {e}")
            return 500
            
    async def run(self, session: aiohttp.ClientSession, delay_range: tuple[float, float]):
        """Continuously send emojis with random delays."""
        while self.running:
            status = await self.send_emoji(session)
            print(f"Client {self.client_id}: Sent emoji, status: {status}")
            # Random delay between requests to simulate realistic usage
            delay = random.uniform(*delay_range)
            await asyncio.sleep(delay)

async def main():
    parser = argparse.ArgumentParser(description='Emoji Client Simulator')
    parser.add_argument('--num-clients', type=int, default=5, help='Number of concurrent clients')
    parser.add_argument('--server-url', type=str, default='http://localhost:5000', help='Server URL')
    parser.add_argument('--min-delay', type=float, default=0.5, help='Minimum delay between requests (seconds)')
    parser.add_argument('--max-delay', type=float, default=2.0, help='Maximum delay between requests (seconds)')
    args = parser.parse_args()

    # Create clients
    clients: List[EmojiClient] = []
    for _ in range(args.num_clients):
        client_id = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        clients.append(EmojiClient(args.server_url, client_id))
    
    # Handle graceful shutdown
    shutdown_event = asyncio.Event()
    
    # Statistics tracking - make it global accessible
    request_count = 0
    start_time = datetime.datetime.now()
    
    # Create a counter lock for thread safety
    count_lock = asyncio.Lock()
    
    async def increment_counter():
        nonlocal request_count
        async with count_lock:
            request_count += 1
    
    # Modified EmojiClient run method
    async def client_run(client, session, delay_range):
        nonlocal request_count
        while client.running:
            status = await client.send_emoji(session)
            print(f"Client {client.client_id}: Sent emoji, status: {status}")
            
            # Increment counter safely
            async with count_lock:
                request_count += 1
            
            delay = random.uniform(*delay_range)
            await asyncio.sleep(delay)
    
    def signal_handler():
        print("\nShutdown signal received. Stopping clients...")
        for client in clients:
            client.running = False
        shutdown_event.set()
    
    # Platform-specific signal handling
    if platform.system() != 'Windows':
        # Unix-like systems (Linux, macOS)
        for sig in (signal.SIGINT, signal.SIGTERM):
            asyncio.get_event_loop().add_signal_handler(sig, signal_handler)
    else:
        # Windows - use different approach
        def windows_signal_handler(signum, frame):
            print("\nShutdown signal received. Stopping clients...")
            for client in clients:
                client.running = False
            # Use asyncio.create_task to set the event from a non-async context
            loop = asyncio.get_event_loop()
            loop.call_soon_threadsafe(shutdown_event.set)
        
        signal.signal(signal.SIGINT, windows_signal_handler)
        if hasattr(signal, 'SIGBREAK'):
            signal.signal(signal.SIGBREAK, windows_signal_handler)
    
    async def print_stats():
        nonlocal request_count
        while not shutdown_event.is_set():
            await asyncio.sleep(5)
            async with count_lock:
                current_count = request_count
            duration = (datetime.datetime.now() - start_time).total_seconds()
            rate = current_count / duration if duration > 0 else 0
            print(f"\n=== Statistics ===")
            print(f"Runtime: {duration:.1f}s")
            print(f"Total requests: {current_count}")
            print(f"Request rate: {rate:.2f} requests/sec")
            print(f"Active clients: {len([c for c in clients if c.running])}")
            print("==================\n")
    
    # Create a single session for all clients
    async with aiohttp.ClientSession() as session:
        # Start all clients with modified run method
        tasks: Set[asyncio.Task] = set()
        
        # Add client tasks
        for client in clients:
            task = asyncio.create_task(
                client_run(client, session, (args.min_delay, args.max_delay))
            )
            tasks.add(task)
        
        # Add statistics task
        stats_task = asyncio.create_task(print_stats())
        tasks.add(stats_task)
        
        print(f"Started {len(clients)} emoji clients")
        print("Press Ctrl+C to stop...")
        
        try:
            # Wait for shutdown signal or tasks to complete
            if platform.system() == 'Windows':
                # On Windows, we need to handle shutdown differently
                while not shutdown_event.is_set():
                    await asyncio.sleep(0.1)
            else:
                # On Unix systems, wait for shutdown event
                await shutdown_event.wait()
        except KeyboardInterrupt:
            # Fallback for Windows
            print("\nKeyboard interrupt received. Stopping clients...")
            for client in clients:
                client.running = False
        finally:
            # Cancel all tasks
            for task in tasks:
                task.cancel()
            
            # Wait for tasks to finish
            await asyncio.gather(*tasks, return_exceptions=True)
            print("All clients stopped.")

if __name__ == "__main__":
    asyncio.run(main())
