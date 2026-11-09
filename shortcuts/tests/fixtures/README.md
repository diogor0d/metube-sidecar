# Native test fixtures

`fixture.mp4` and `fixture.jpg` are tiny synthetic media files generated solely
for the local Shortcut harness. They contain no user media or production data.
`native_test.py prepare` copies them into the selected work directory only when
the corresponding destination file does not already exist. Keep replacement
fixtures synthetic and suitable for redistribution with this public repository.

`index.html` exposes that clip and JPEG to the disposable Docker integration
stack. Its 128-by-128 height/width metadata matches the video: yt-dlp needs known
height metadata to apply a resolution ceiling. The hostname `fixture` is a
logical service alias inside that test network.
