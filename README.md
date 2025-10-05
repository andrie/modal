Testing ideas using modal.com

https://modal.com/

## App

A slimlined app with better performance, as a result of using the modal dict instead of retrieving from SQLite

``` shell
modal run ./new-app.py
modal serve ./new-app.py
modal deploy ./new-app.py
```

You can also selectively trigger functions in the modal app:

``` shell
# Run everything (default)
modal run new-app.py

# Only update flow data
modal run new-app.py --cache-flow --no-cache-weather --no-guidance

# Only update weather and guidance
modal run new-app.py --no-cache-flow --cache-weather --guidance

# Only guidance (using cached data)
modal run new-app.py --no-cache-flow --no-cache-weather --guidance
```


The quarto doc is deployed on Posit Connect Cloud at https://connect.posit.cloud/andrie/content/018e2819-5587-2875-2c79-3de976009189

The app is deployed via github.  Use the Connect Cloud interface to trigger updates.