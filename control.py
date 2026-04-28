import libsonic
import subprocess
from urllib.parse import urlencode

# Function to construct the authenticated stream URL for external players
def get_jukebox_url(conn, song_id):
    # Retrieve internal auth parameters including the token and salt
    query = conn._getBaseQdict()
    query['id'] = song_id
    
    # Define the Subsonic stream view
    view = 'stream.view'
    
    # Assemble the full URL string
    # Using the internal connection attributes from the py-sonic source
    url = f"{conn._baseUrl}:{conn._port}/{conn._serverPath}/{view}?{urlencode(query)}"
    
    return url

# Connection parameters for the 10.42.0.x subnet
# BaseUrl must include the http protocol
server_ip = "http://10.42.0.1"
server_port = 4533
user = "christopher"
password = "72555"

# Initialize the connection object
conn = libsonic.Connection(
    baseUrl=server_ip,
    username=user,
    password=password,
    port=server_port
)

def play_test_song():
    try:
        print("Attempting to fetch a random song from Arch server")
        
        # Get one random song from the library
        response = conn.getRandomSongs(size=1)
        
        if "randomSongs" in response:
            songs = response["randomSongs"].get("song", [])
            if songs:
                track = songs[0]
                song_id = track.get("id")
                title = track.get("title")
                artist = track.get("artist")
                
                # Build the stream URL
                stream_url = get_jukebox_url(conn, song_id)
                
                print(f"Found: {title} by {artist}")
                print(f"Streaming from: {stream_url}")
                
                # Execute mpv on the Pi to play the stream
                # --no-video ensures no window opens on your headless setup
                subprocess.run(["mpv", "--no-video", stream_url])
            else:
                print("No songs found in the library response")
        else:
            print("Unexpected response format from server")
            
    except Exception as error:
        print(f"An error occurred during playback: {error}")

if __name__ == "__main__":
    play_test_song()
