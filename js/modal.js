
async function request(url) {
    const response = await fetch(url);
    const data = await response.json();
    return data;
}

async function updateSunTimes() {
    const data = await request("https://andrie--thames-sunrise.modal.run/");
    const container = document.getElementById('sun-times-table');
    container.innerHTML = '';
    // Transpose the data
    const tdata = [
        data.map(obj => obj.event),
        data.map(obj => obj.time)
    ];
    new gridjs.Grid({
        // columns: ['Event', 'Time'],
        data: tdata
    }).render(container);
 }

// river conditions -----------------------------------------------------

async function fetchRiverConditionsData() {
    const currentTime = Date.now();
    const storedData = localStorage.getItem('data-river-closures');
    const storedTime = localStorage.getItem('time-river-closures');

    if (storedData && storedTime && currentTime < new Date(storedTime)) {
        // If the stored data and time exist and the data is less than 15 minutes old, return the stored data
        data = JSON.parse(storedData);
    } else {
        // Otherwise, fetch the data from the API
        data = await request('https://andrie--thames-conditions.modal.run/');

        // filter data on rows where `To` == 'Molesey Lock'

        // Store the data and the current time in local storage
        localStorage.setItem('data-river-closures', JSON.stringify(data));
        const updateTime = currentTime + 15 * 60 * 1000;
        localStorage.setItem('time-river-closures', updateTime.toString());
    }
    const sub = data.filter(row => row.to === 'Molesey Lock');
    return sub;
}

async function updateRiverConditions(element = 'river-closures-table') {
    const data = await fetchRiverConditionsData()
    const container = document.getElementById(element);
    container.innerHTML = '';
    // remove date columns
    data.forEach(row => row.reach = row.from + ' to ' + row.to);   
    data.forEach(row => {delete row.date; delete row.from; delete row.to});
    
    new gridjs.Grid({
        columns: ['reach', 'condition'],
        data: data
    }).render(container);
}

// weather ---------------------------------------------------------------

async function fetchWeatherData() {
    var storedData;
    const currentTime = Date.now();
    const storedTime = localStorage.getItem('time-weather');
    
    if (storedTime && currentTime < new Date(storedTime)) {
        // If the stored data and time exist and the data is less than 15 minutes old, return the stored data
        data = localStorage.getItem('data-weather');
    } else {
        // Otherwise, fetch the data from the API
        data = await request('https://andrie--weather.modal.run/');
        // Store the data and the current time in local storage
        localStorage.setItem('data-weather', JSON.stringify(data));
        const updateTime = currentTime + 15 * 60 * 1000;
        localStorage.setItem('time-weather', updateTime.toString());
    }
    // data = await request('https://andrie--weather-dev.modal.run/');
    data = JSON.parse(data);
    const sub = data
    return sub;
}

async function updateWeather(element = 'weather-forecast-table') {
    const data = await fetchWeatherData();
    // const times = Object.values(data.time);
    console.log(data)
    const times = Object.values(data.time).map(time => {
        const date = new Date(time);
        // date.setHours(date.getHours() - 1); // Convert to British local time
        return new Intl.DateTimeFormat('en-GB', {
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit'
        }).format(date);
    });
    const descriptions = Object.values(data.description);
    const icons = Object.values(data.icon);
    const temperature = Object.values(data.screenTemperature).map(
        t => Math.round(t) + '°C'
    );
    const windSpeed = Object.values(data.windSpeed10m).map(v => Math.round(v*3.6))
    const windGust  = Object.values(data.windGustSpeed10m).map(v => Math.round(v*3.6))
    const windDir   = Object.values(data.windDirectionFrom10m)
    const rain = Object.values(data.probOfPrecipitation).map(p => p + '%' )

    const wind = windSpeed

    const container = document.getElementById(element);
    container.innerHTML = '';

    const combinedData = times.map((time, index) =>
        [
            Object(data.time)[index], 
            descriptions[index], 
            icons[index],
            temperature[index],
            rain[index],
            wind[index] + ' - ' + windGust[index],
            // windGust[index],
            windDir[index],
        ]
    ).filter(row => {
        const rowTime = new Date(row[0]);
        return rowTime >= new Date(); // Only keep rows where time is in the future
    });

    const wrapper = document.createElement('div');
    wrapper.style.maxHeight = '16rem'; // Adjust this value to fit 8 rows
    wrapper.style.overflow = 'auto';
    container.appendChild(wrapper);

    new gridjs.Grid({
        columns: [
            'time', 
            'description', 
            {
                name: 'icon',
                formatter: (cell) => gridjs.h('i', { className: `wi ${cell}` })
            },
            'temp',
            'rain',
            'wind (km/h)',
            {
                name: 'from',
                formatter: (cell) => gridjs.h('i', { className: `wi wi-wind from-${cell}-deg` })
            },
        ],
        data: combinedData,
    }).render(wrapper);
}



// flow rate -------------------------------------------------------------

async function updateFlowRate(station = "Walton", element = 'flow-rate-table') {

    // const station_search = station
    // const station = station_search + " Lock";

    const data = await request('https://andrie--flow.modal.run/?station=' + station);
    const container = document.getElementById(element);
    container.innerHTML = '';

    pdata = data.map(row => {
        return {
            x: row.dateTime,
            y: row.value
        }
    });
    const pData = [{
        x: data.map(row => row.dateTime),
        y: data.map(row => row.value),
        mode: 'lines+markers',
        marker: {
            size: 4  // Make the markers smaller
        },
        line: {
            shape: 'spline'  // Make the lines curved
        }
        
    }];
    Plotly.newPlot(container, pData,
        {
            title: 'Flow rate at ' + station,
            yaxis: { title: 'cumecs' }
        }
    );
}


// lock level ------------------------------------------------------------

async function updateLockLevel(station_search = "Sunbury") {

    // const station_search = "Molesey"
    const station = station_search + " Lock";

    const data = await request('https://andrie--thames-water-level.modal.run/?station=' + station_search);
    const container = document.getElementById('lock-level-table');
    container.innerHTML = '';

    pdata = data.map(row => {
        return {
            x: row.dateTime,
            y: row.value
        }
    });
    const pData = [{
        x: data.map(row => row.dateTime),
        y: data.map(row => row.value),
        mode: 'lines+markers',
        marker: {
            size: 4  // Make the markers smaller
        },
        line: {
            shape: 'spline'  // Make the lines curved
        }
        
    }];
    Plotly.newPlot(container, pData,
        {
            title: 'Water level at ' + station,
            yaxis: { title: 'Level (mASD)' }
        }
    );
}


// spinners ---------------------------------------------------------------

addSpinnerId = function(id) {
    const container = document.getElementById(id);
    const spinner = document.createElement('div');
    spinner.className = 'spinner';
    container.appendChild(spinner);
}

addSpinner = function(el) {
    const spinner = document.createElement('div');
    spinner.className = 'spinner';
    el.appendChild(spinner);
}

// window.onload ----------------------------------------------------------

window.onload = async function() {
    Array.from(
        document.getElementsByClassName('autospinner')
    ).forEach(function(el) {
        addSpinner(el);
    });
    await Promise.all([
        updateSunTimes(),
        updateRiverConditions(),
        updateLockLevel("Sunbury"),
        updateFlowRate("Walton", "flow-rate-table"),
        updateWeather('weather-forecast-table'),
    ]);
 }