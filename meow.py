from thresholdfloor import ThresholdFloor as tf


# Spins clockwise
floor = tf("meow meow london", 54.00, 2.00, "Europe/London")
sigil = floor.sigil() # Generate and display current sigil

floor = tf("meow meow london", 45.00, 2.00, "Europe/London")
sigil = floor.sigil() # Generate and display current sigil

floor = tf("meow meow london", 36.00, 2.00, "Europe/London")
sigil = floor.sigil() # Generate and display current sigil

floor = tf("meow meow london", 27.00, 2.00, "Europe/London")
sigil = floor.sigil() # Generate and display current sigil

floor = tf("meow meow london", 18.00, 2.00, "Europe/London")
sigil = floor.sigil() # Generate and display current sigil

floor = tf("meow meow london", 9.00, 2.00, "Europe/London")
sigil = floor.sigil() # Generate and display current sigil

floor = tf("meow meow london", 0.00, 2.00, "Europe/London")
sigil = floor.sigil() # Generate and display current sigil

floor = tf("meow meow london", -9.00, 2.00, "Europe/London")
sigil = floor.sigil() # Generate and display current sigil

floor = tf("meow meow london", -18.00, 2.00, "Europe/London")
sigil = floor.sigil() # Generate and display current sigil

floor = tf("meow meow london", -27.00, 2.00, "Europe/London")
sigil = floor.sigil() # Generate and display current sigil

floor = tf("meow meow london", -36.00, 2.00, "Europe/London")
sigil = floor.sigil() # Generate and display current sigil

floor = tf("meow meow london", -45.00, 2.00, "Europe/London")
sigil = floor.sigil() # Generate and display current sigil

floor = tf("meow meow london", -54.00, 2.00, "Europe/London")
sigil = floor.sigil() # Generate and display current sigil

floor = tf("sleep", latitude=31.871, longitude=8.443, tz="Asia/Jerusalem")
sigil = floor.sigil() # Generate and display current sigil

floor = tf("sleepwalkerr", latitude=31.871, longitude=14.443, tz="Asia/Jerusalem")
sigil = floor.sigil() # Generate and display current sigil

floor = tf("walkerr", latitude=31.871, longitude=22.443, tz="Asia/Jerusalem")

sigil = floor.sigil() # Generate and display current sigil

floor = tf("Jericho", latitude=31.871, longitude=35.443, tz="Asia/Jerusalem")
sigil = floor.sigil() # Generate and display current sigil

floor = tf(name="meow meow tehran", latitude=35.6892, longitude=51.3890, tz="Asia/Tehran")#, elevation_m=1200) # Leave the elevation off for auto topography based on lat an lonm
sigil = floor.sigil() # Generate and display current sigil



floor = tf(name="meow meow indus maybe", latitude=42.6892, longitude=75.3890, tz="Asia/Tehran")#, elevation_m=1200) # Leave the elevation off for auto topography based on lat an lonm
sigil = floor.sigil() # Generate and display current sigil

floor = tf(name="meow meow tartarus", latitude=44.6892, longitude=90.3890, tz="Asia/Tehran")#, elevation_m=1200) # Leave the elevation off for auto topography based on lat an lonm
sigil = floor.sigil() # Generate and display current sigil



floor = tf("meow meow beijing", 39.9075, 116.3972, "Asia/Shanghai", elevation_m=50)
sigil = floor.sigil() # Generate and display current sigil

floor = tf("meow meow tokyo", 35.68972, 139.69222, "Asia/Tokyo")
sigil = floor.sigil() # Generate and display current sigil

floor = tf("meow meow hongkong", 22.3027, 114.1772, "Asia/Hong_Kong", elevation_m=958)
sigil = floor.sigil() # Generate and display current sigil

floor = tf(name="meow meow waterville", latitude=0.6892, longitude=140.3890, tz="Europe/London")#, elevation_m=1200) # Leave the elevation off for auto topography based on lat an lonm

sigil = floor.sigil() # Generate and display current sigil


floor = tf("Basin", 45.203998, -123.722058, "US/Pacific", elevation_m=700)

sigil = floor.sigil() # Generate and display current sigilz


sigil = floor.sigil() # Generate and display current sigil
