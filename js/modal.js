const dev_mode = false;
if (dev_mode) {
    modal_url = "https://andrie--conditions-dev.modal.run/"
} else {
    modal_url = "https://andrie--conditions.modal.run/"
}

async function request(url) {
    // const response = await fetch(url, { mode: 'no-cors' });
    const response = await fetch(url);
    return response.json();
}


function getCache(cache_name, expiry = 15) {
    storedData = localStorage.getItem(`data-${cache_name}`);
    storedTime = localStorage.getItem(`time-${cache_name}`);
    currentTime = Date.now()
    expiryTime = parseInt(storedTime) + expiry * 60 * 1000;
    if (storedData && storedTime && expiryTime < currentTime) {
        // If the stored data and time exist and the data is less than 15 minutes old, return the stored data
        return JSON.parse(storedData);
    }
    return null;   
}

function setCache(data, cache_name, time = Date.now()) {
    localStorage.setItem(`data-${cache_name}`, JSON.stringify(data));
    localStorage.setItem(`time-${cache_name}`, time);
    return true
}

async function request_modal(parms, cache_name, expiry = 15) {
    data = getCache(cache_name, expiry = expiry)
    if (!data) {
        data = await request(`${modal_url}?${parms}`);
        if (data) { setCache(data, cache_name); }
    }
    return data;
}

function checkValidElement(element) {
    const container = document.getElementById(element)
    if (!container) {
        console.log(`No container found for ${element}`);
        return null
    };
    return container;
}

async function displaySunTimes(element = 'sun-times-table') {
    const container = checkValidElement(element)
    if (!container) { return null };

    const data = await request_modal('metric=sunrise', 'sunrise');
    // console.log(data)
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

async function displayRiverConditions(element = 'river-conditions-table') {
    const data = await request_modal('metric=boards', 'boards')
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


async function updateWeather(element = 'weather-forecast-table') {
    dataString = await request_modal("metric=weather", "weather")
    data = JSON.parse(data)
    // console.log(data)
    const times = Object.values(data.time).map(time => {
        const date = new Date(time);
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

    const transposedData = combinedData[0].map((_, colIndex) => 
        combinedData.map(row => row[colIndex])
    );

    // Extract the first row for column headers and format the time
    const columnHeaders = transposedData[0].map(timestamp => {
        const date = new Date(timestamp);
        return date.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
    });

    const dataWithoutHeaders = transposedData.slice(1);

    // Apply formatter to wind direction row
    dataWithoutHeaders[5] = dataWithoutHeaders[5].map(cell => 
        gridjs.h('i', { className: `wi wi-wind from-${cell}-deg` })
    );
    
    // Apply formatter to the weather symbols row
    dataWithoutHeaders[1] = dataWithoutHeaders[1].map(cell => 
        gridjs.h('i', { className: `wi ${cell}` })
    );
    
    new gridjs.Grid({
        columns: columnHeaders,
        data: dataWithoutHeaders,
    }).render(wrapper);
}



// flow rate -------------------------------------------------------------

async function updateFlowRate(station = "Walton", element = 'flow-rate-table') {

    const data = await request(`${modal_url}?metric=flow&station=${station}`);
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

async function updateLockLevel(station = "Sunbury", element = "level-sunbury") {

    const container = document.getElementById(element);
    const data = await request(`${modal_url}?metric=level&station=${station}`);
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

async function update_hcc_summary() {
    const data = await request_modal('metric=hcc_summary', 'hcc_summary');
    return data;
}

async function update_hcc_all() {
    const data = await request_modal('metric=hcc_all', 'hcc_all');
    return data;
}

// window.onload ----------------------------------------------------------

window.onload = async function() {
    Array.from(
        document.getElementsByClassName('autospinner')
    ).forEach(function(el) {
        addSpinner(el);
    });

    const summary = false;
    if (summary) {
        hcc_data = await update_hcc_summary()
    } else {   
        hcc_data = await update_hcc_all()
    }
    Object.entries(hcc_data).forEach(([name, data]) => {
        setCache(data, name)
    })
    displaySunTimes('sun-times-table');
    displayRiverConditions('river-conditions-table')
    updateFlowRate("Walton", "flow-rate-walton")
    if (!summary) {
        updateLockLevel("Sunbury", "level-sunbury")
        updateLockLevel("Molesey", "level-molesey")
        updateFlowRate("Kingston", "flow-rate-kingston")
        updateWeather('weather-forecast-table')
    }
    
 }