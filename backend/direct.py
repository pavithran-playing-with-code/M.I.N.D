# The direct road: phone <-> laptop with WebRTC (the way Google Meet / Chrome Remote Desktop connect), no VPN.
# The phone and the laptop are introduced once through the normal (fingerprint-locked) phone server, then they
# talk straight to each other, encrypted, instead of going India -> Paris (Tailscale Funnel) -> India for every
# tap, letter and picture. On the same Wi-Fi it stays inside the Wi-Fi (no internet data used).
# If a network blocks direct links (some mobile networks do), the phone simply keeps using the normal road.
#
# The live view and the remote run here UNCHANGED: a data channel is wrapped to look like the web socket
# they already use (Channel). Pictures bigger than one data-channel message go in pieces (PIECE).
import asyncio
from aiortc import RTCPeerConnection, RTCSessionDescription, RTCConfiguration, RTCIceServer

# Free public "what's my address" helpers (STUN): they only tell each side its internet address, no data passes them
STUN = [RTCIceServer(urls="stun:stun.l.google.com:19302"), RTCIceServer(urls="stun:stun.cloudflare.com:3478")]
PIECE = 60000  # bytes per message (Chrome takes up to ~256 KB, smaller is safer)
links = set()  # the open links (kept so they aren't thrown away while running)

class Channel:
    # A data channel that behaves like the web socket the live view / remote handlers expect
    def __init__(self, channel):
        self.channel = channel
        self.inbox = asyncio.Queue()
        channel.on("message", self.inbox.put_nowait)
        channel.on("close", lambda: self.inbox.put_nowait(None))

    async def accept(self):
        pass

    async def receive(self):
        # The next message as it came: text (str) or file bytes (bytes)
        message = await self.inbox.get()
        if message is None:
            raise ConnectionError("The direct link closed.")
        return message

    async def receive_text(self):
        message = await self.receive()
        return message if isinstance(message, str) else message.decode("utf-8", "ignore")

    def open(self):
        if self.channel.readyState != "open":
            raise ConnectionError("The direct link closed.")

    async def send_text(self, text):
        self.open()
        self.channel.send(text)

    async def send_bytes(self, data):
        # In pieces: the first byte says 1 = last piece, 0 = more coming (the phone joins them)
        self.open()
        for start in range(0, len(data), PIECE):
            last = start + PIECE >= len(data)
            self.channel.send(bytes([1 if last else 0]) + data[start:start + PIECE])

    async def close(self):
        self.channel.close()

async def answer(offer, handlers):
    # The phone's offer in, the laptop's answer out. handlers: channel name -> the code that runs it
    link = RTCPeerConnection(RTCConfiguration(iceServers=STUN))
    links.add(link)

    @link.on("datachannel")
    def new_channel(channel):
        run = handlers.get(channel.label)
        if run:
            asyncio.ensure_future(run(Channel(channel)))

    @link.on("connectionstatechange")
    async def changed():
        if link.connectionState == "connected":
            print("(Phone direct link: connected)")
        if link.connectionState in ("failed", "closed"):
            links.discard(link)
            await link.close()

    await link.setRemoteDescription(RTCSessionDescription(sdp=offer, type="offer"))
    await link.setLocalDescription(await link.createAnswer())  # (finds all the laptop's addresses first)
    return link.localDescription.sdp
