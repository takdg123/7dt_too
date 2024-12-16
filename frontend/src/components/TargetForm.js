import React, { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import '../styles/TargetForm.css';
import {
    Autocomplete,
    Alert,
    TextField,
    Button,
    RadioGroup,
    FormControlLabel,
    Radio,
    Checkbox,
    Dialog,
    DialogTitle,
    DialogContent,
    DialogActions,
    Snackbar,
    CircularProgress,
} from '@mui/material';

import 'chartjs-adapter-date-fns';

import {
    Chart as ChartJS,
    LinearScale,
    Title,
    Tooltip,
    ScatterController,
    LineController,
    LineElement,
    PointElement,
    CategoryScale,
    TimeScale,
    Legend
} from 'chart.js';
import annotationPlugin from 'chartjs-plugin-annotation';

import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import ExpandLessIcon from '@mui/icons-material/ExpandLess';
import SpecMode from './SpecMode';
import DeepMode from './DeepMode';
import DetailedSettings from './DetailedSettings';

ChartJS.register(
    LinearScale,
    Title,
    Tooltip,
    ScatterController,
    LineController,
    LineElement,
    PointElement,
    CategoryScale,
    TimeScale,
    Legend,
    annotationPlugin
);

const TargetForm = () => {
    const [targets, setTargets] = useState([]);
    const [target, setTarget] = useState('');
    const [ra, setRa] = useState('');
    const [dec, setDec] = useState('');
    const [exposure, setExposure] = useState('300');
    const [obsmode, setObsmode] = useState('Spec'); 
    const [comments, setComments] = useState('');
    const [abortObservation, setAbortObservation] = useState(false); // Track checkbox state
    const [requester, setRequester] = useState(''); // Track requester email

    const [wavelengths, setWavelengths] = useState([]);
    const [filters, setFilters] = useState([]);
    const [specFileOptions, setSpecFileOptions] = useState(['specall.specmode']);
    const [selectedSpecFile, setSelectedSpecFile] = useState('specall.specmode');
    const [selectedFilters, setSelectedFilters] = useState(['g']); // For checkboxes
    const [selectedTelNumber, setSelectedTelNumber] = useState(10); // For dropdown
    const [staraltData, setStaraltData] = useState(null);

    const [isCustomTarget, setIsCustomTarget] = useState(true);
    const [isCollapsed, setIsCollapsed] = useState(true); // Collapse state for mode options
    const [isDetailCollapsed, setIsDetailCollapsed] = useState(true); // Collapse state for mode options
    const [isStaraltCollapsed, setIsStaraltCollapsed] = useState(false); // Collapse state for mode options
    const [isDialogOpen, setIsDialogOpen] = useState(false); // Dialog state
    const [isLoading, setIsLoading] = useState(false);

    const [error, setError] = useState('');
    const [successMessage, setSuccessMessage] = useState('');

    const [detailedSettings, setDetailedSettings] = useState({
        singleFrameExposure: 60, // Default 60 seconds
        imageCount: 5, // Default exposure time / 60
        priority: 50, // Default 50
        gain: 2750, // Default 2750
        binning: 1, // Default 1
        obsStartTime: '', // Default empty
    });

    const chartRef = useRef(null);
    const staraltChartRef = useRef(null);
    

    useEffect(() => {
        axios
            .get('/api/targets')
            .then((response) => setTargets(response.data))
            .catch((error) => console.error('Error fetching targets:', error));
    }, []);

    useEffect(() => {
        if (obsmode === 'Spec') {
            axios
                .get('/api/spec-options')
                .then((response) => setSpecFileOptions(response.data))
                .catch((error) => console.error('Error fetching spec file options:', error));
        }
    }, [obsmode]);

    useEffect(() => {
        if (selectedSpecFile) {
            axios
                .get(`/api/spec-file?file=${selectedSpecFile}`)
                .then((response) => {
                    setWavelengths(response.data.wavelengths);
                    setFilters(response.data.filters);
                })
                .catch((error) => console.error('Error fetching spec file data:', error));
        }
    }, [selectedSpecFile]);


    useEffect(() => {
        const raNum = parseFloat(ra);
        const decNum = parseFloat(dec);
        if (!isNaN(raNum) && !isNaN(decNum)) {
            const query = `ra=${raNum}&dec=${decNum}&objname=${encodeURIComponent(target)}&target_minalt=30&target_minmoonsep=40`;
            fetch(`/api/staralt_data?${query}`)
                .then((response) => response.json())
                .then((data) => {
                    setStaraltData(data);
                    console.log("Received staralt data:", data);
                })
                .catch((error) => console.error("Error fetching staralt data:", error));
        }
    }, [ra, dec, target]);

    useEffect(() => {
        if (!staraltData || !staraltChartRef.current) return;

        const {
            objname,
            target_times, target_alts,
            moon_times, moon_alts,
            sun_times, sun_alts,
            color_target,
            tonight,
            target_minalt,
            target_minmoonsep
        } = staraltData;

        // Convert times to Date objects
        const targetData = target_times.map((t, i) => ({ x: new Date(t), y: target_alts[i] }));
        const moonData = moon_times.map((t, i) => ({ x: new Date(t), y: moon_alts[i] }));
        const sunData = sun_times.map((t, i) => ({ x: new Date(t), y: sun_alts[i] }));

        // Map color codes to CSS colors
        const mappedColorTarget = color_target.map(c => {
            if (c === 'r') return 'red';
            if (c === 'k') return 'black';
            if (c === 'g') return 'green';
            return c; // fallback if needed
        });

        // Convert night times to Date objects
        const sunsetNight = new Date(tonight.sunset_night);
        const sunriseNight = new Date(tonight.sunrise_night);
        const sunsetCivil = new Date(tonight.sunset_civil);
        const sunriseCivil = new Date(tonight.sunrise_civil);

        const targetDataset = {
            label: 'Target',
            data: targetData,
            pointBackgroundColor: mappedColorTarget,
            borderColor: 'black',
            showLine: false,
            pointRadius: 2
        };

        const moonDataset = {
            label: 'Moon',
            data: moonData,
            borderColor: 'blue',
            backgroundColor: 'blue',
            showLine: false,
            pointRadius: 1
        };

        const sunDataset = {
            label: 'Sun',
            data: sunData,
            borderColor: 'red',
            backgroundColor: 'red',
            showLine: false,
            pointRadius: 1
        };

        const annotations = {
            // Vertical line at night start
            nightStartLine: {
                type: 'line',
                xMin: sunsetNight.getTime(),
                xMax: sunsetNight.getTime(),
                borderColor: 'black',
                borderWidth: 1,
                label: {
                    enabled: true,
                    content: 'Night start',
                    position: 'start',
                    yAdjust: -20
                }
            },
            // Vertical line at night end
            nightEndLine: {
                type: 'line',
                xMin: sunriseNight.getTime(),
                xMax: sunriseNight.getTime(),
                borderColor: 'black',
                borderWidth: 1,
                label: {
                    enabled: true,
                    content: 'Night end',
                    position: 'start',
                    yAdjust: -20
                }
            },
            // Shaded nighttime region
            nightBox: {
                type: 'box',
                xMin: sunsetNight.getTime(),
                xMax: sunriseNight.getTime(),
                yMin: 0,
                yMax: 90,
                backgroundColor: 'rgba(0,0,0,0.3)',
                drawTime: 'beforeDatasetsDraw'
            },
            // Shaded civil twilight region
            civilBox: {
                type: 'box',
                xMin: sunsetCivil.getTime(),
                xMax: sunriseCivil.getTime(),
                yMin: 0,
                yMax: 90,
                backgroundColor: 'rgba(0,0,0,0.1)',
                drawTime: 'beforeDatasetsDraw'
            },
            // Fill below minimum altitude line (red zone)
            minAltFill: {
                type: 'box',
                xMin: sunsetNight.getTime(),
                xMax: sunriseNight.getTime(),
                yMin: 0,
                yMax: target_minalt,
                backgroundColor: 'rgba(255,0,0,0.3)',
                drawTime: 'beforeDatasetsDraw',
                label: {
                    enabled: true,
                    content: 'Observation limit',
                    position: 'center',
                    yAdjust: -50,
                    font: { weight: 'bold', size: 12 },
                    color: 'darkred'
                }
            },
            // Add a text annotation with criteria
            criteriaText: {
                type: 'label',
                xValue: new Date(sunsetNight.getTime() - 0.7 * 3600000), // 0.7 hours before night start
                yValue: 80,
                backgroundColor: 'rgba(255,255,255,0.7)',
                borderColor: 'black',
                borderWidth: 1,
                color: 'black',
                font: { size: 10, weight: 'bold' },
                textAlign: 'left',
                content: [
                    `Current observation criteria:`,
                    `- Altitude > ${target_minalt} deg`,
                    `- Moon separation > ${target_minmoonsep} deg`
                ]
            }
        };

        // If the chart instance exists, update data and annotations
        if (staraltChartRef.current._chart) {
            const chart = staraltChartRef.current._chart;
            chart.data.datasets = [sunDataset, moonDataset, targetDataset];
            chart.options.plugins.title.text = objname ? `Altitude of ${objname}` : 'Altitude of the Target';
            chart.options.plugins.annotation.annotations = annotations;
            chart.update();
        } else {
            // Otherwise, create a new chart
            const ctx = staraltChartRef.current.getContext('2d');
            const chart = new ChartJS(ctx, {
                type: 'line',
                data: {
                    datasets: [sunDataset, moonDataset, targetDataset]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false, // Allow the chart to fill its container
                    layout: {
                        padding: 10
                    },
                    scales: {
                        x: {
                            type: 'time',
                            time: {
                                unit: 'hour'
                            },
                            title: {
                                display: true,
                                text: 'Time (UTC)'
                            }
                        },
                        y: {
                            title: {
                                display: true,
                                text: 'Altitude [deg]'
                            },
                            min: 0,
                            max: 90
                        }
                    },
                    plugins: {
                        title: {
                            display: true,
                            text: objname ? `Altitude of ${objname}` : 'Altitude of the Target',
                        },
                        legend: {
                            display: true,
                            position: 'chartArea',
                            labels: {
                                boxWidth: 10,
                                boxHeight: 10,
                                padding: 10,
                            }
                        },
                        tooltip: {
                            mode: 'nearest',
                            intersect: false
                        },
                        annotation: {
                            annotations: annotations
                        }
                    },
                    interaction: {
                        mode: 'nearest',
                        intersect: false
                    }
                }
            });
            staraltChartRef.current._chart = chart;
        }
    }, [staraltData, isStaraltCollapsed]);

    useEffect(() => {
        if (!chartRef.current) return;

        const ctx = chartRef.current.getContext('2d');
        let wavelengthChart = ChartJS.getChart(ctx);

        if (!wavelengthChart) {
            wavelengthChart = new ChartJS(ctx, {
                type: 'scatter',
                data: { labels: [''], datasets: [] },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        x: { type: 'linear', min: 3500, max: 9500, title: { display: false } },
                        y: { display: false },
                    },  
                    plugins: { legend: { display: false } },
                },
                plugins: [
                    {
                        id: 'customSpans',
                        beforeDraw: (chart) => {
                            const ctx = chart.ctx;
                            const xScale = chart.scales.x;
                            wavelengths.forEach((wav) => {
                                const xMin = xScale.getPixelForValue((wav - 12.5) * 10);
                                const xMax = xScale.getPixelForValue((wav + 12.5) * 10);
                                const xCenter = xScale.getPixelForValue(wav * 10);
                                
                                // Create gradient
                                const gradient = ctx.createLinearGradient(xMin, 0, xMax, 0);
                                gradient.addColorStop(0, 'black');
                                gradient.addColorStop(0.1, 'darkgreen');
                                gradient.addColorStop(0.5, 'green');
                                gradient.addColorStop(0.9, 'darkgreen');
                                gradient.addColorStop(1, 'black');

                                // Draw the gradient span
                                ctx.fillStyle = gradient;
                                ctx.fillRect(
                                    xMin,
                                    chart.chartArea.top,
                                    xMax - xMin,
                                    chart.chartArea.bottom - chart.chartArea.top
                                );
                                // Draw the center line
                                ctx.strokeStyle = 'darkgreen'; // You can change the color as needed
                                ctx.beginPath();
                                ctx.moveTo(xCenter, chart.chartArea.top);
                                ctx.lineTo(xCenter, chart.chartArea.bottom);
                                ctx.stroke();
                                
                                // Draw the horizontal center line
                                const yCenter = (chart.chartArea.top + chart.chartArea.bottom) / 2;
                                ctx.beginPath();
                                ctx.moveTo(xMin, yCenter);
                                ctx.lineTo(xMax, yCenter);
                                ctx.stroke();
                            });
                        },
                    },
                ],
            });
        } else {
            wavelengthChart.data.datasets = [];
            wavelengthChart.update();
        }

        return () => wavelengthChart?.destroy();
    }, [wavelengths, obsmode, isCollapsed]);


    const handleSubmit = async (e) => {
        e.preventDefault();

        setIsLoading(true);
        setError('');

        try {
            await axios.post('http://127.0.0.1:5000/api/send_email', {
                requester,
                target,
                ra,
                dec,
                exposure,
                obsmode,
                comments,
                abortObservation,
                ...detailedSettings,
                ...(obsmode === 'Deep' && { selectedFilters, selectedTelNumber }),
                ...(obsmode === 'Spec' && { selectedSpecFile })
            });
            setSuccessMessage('Email sent successfully!');
            setError('');
            setIsDialogOpen(false); // Close dialog on success
        } catch (error) {
            setError('Failed to send the email. Please try again.');
        } finally {
            setIsLoading(false); // Stop loading
        }
    };

    const handleInputChange = (event, value) => {
        setTarget(value);
        const selectedTarget = targets.find((t) => t.name === value);
        if (selectedTarget) {
            setRa(selectedTarget.ra);
            setDec(selectedTarget.dec);
            setIsCustomTarget(false);
        } else {
            setRa('');
            setDec('');
            setIsCustomTarget(true);
        }
    };

    const handleExposureChange = (newExposure) => {
        const { imageCount } = detailedSettings;
        const newSingleFrameExposure = newExposure / imageCount;
        setDetailedSettings((prev) => ({
            ...prev,
            singleFrameExposure: newSingleFrameExposure,
        }));
        setExposure(newExposure);
    };

    const handleBlur = () => {
        // Remove leading zeros unless they are part of a decimal number
        const trimmedExposure = exposure.replace(/^0+(?=\d)/, '').replace(/^0*(\.\d+)/, '0$1');
        setExposure(trimmedExposure);
    };


    const handleCheckboxChange = (filter) => {
        setSelectedFilters((prev) =>
            prev.includes(filter)
                ? prev.filter((item) => item !== filter) // Remove filter if unchecked
                : [...prev, filter] // Add filter if checked
        );
    };
    
    const toggleCollapse = () => {
        setIsCollapsed(!isCollapsed);
    };

    const toggleDetailCollapse = () => {
        setIsDetailCollapsed(!isDetailCollapsed);
    };

    const toggleStaraltCollapse = () => {
        setIsStaraltCollapsed(!isStaraltCollapsed);
    };

    const toggleDialog = () => {
        // Validate required fields
        if (!ra || !dec || !requester || !target) {
            setError('Fill all required fields: Requester, Target, R.A., Dec.');
            return;
        }

        // Validate email format
        const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        if (!emailRegex.test(requester)) {
            setError('Please enter a valid email address.');
            return;
        }

        // Check if the target is observable
        const isObservable = staraltData.color_target.includes('g');
        if (!isObservable) {
            setError('The entered RA and DEC are not in any observable conditions. Check the visibility plot.');
            return;
        }
        setIsDialogOpen(!isDialogOpen);
    };

    return (
        <div className="container">
            <form onSubmit={handleSubmit} className="form">
                <div className="group-container">
                    <label className="default-label">Requester:</label>
                    <TextField
                        label="Your email address"
                        variant="outlined"
                        value={requester}
                        onChange={(e) => setRequester(e.target.value)}
                        fullWidth
                        className="input-field"
                        size="small"
                        type="email"
                        required
                    />
                </div>
                <div className="group-container">
                    <label className="default-label">Target:</label>
                    <Autocomplete
                        options={targets}
                        getOptionLabel={(option) => option.name || ''}
                        inputValue={target}
                        onInputChange={handleInputChange}
                        renderInput={(params) => (
                            <TextField {...params} label="Target" variant="outlined" fullWidth size="small" required/>
                        )}
                        freeSolo
                        className="input-field"
                    />
                </div>
                <div className="group-container">
                    <label className="default-label">R.A.:</label>
                    <TextField
                        label="hh:mm:ss or degrees"
                        variant="outlined"
                        value={ra}
                        onChange={(e) => setRa(e.target.value)}
                        fullWidth
                        disabled={!isCustomTarget} 
                        className="input-field"
                        size="small"
                        required
                    />
                </div>
                <div className="group-container">
                    <label className="default-label">Dec.:</label>
                    <TextField
                        label="dd:mm:ss or degrees"
                        variant="outlined"
                        value={dec}
                        onChange={(e) => setDec(e.target.value)}
                        fullWidth
                        disabled={!isCustomTarget} 
                        className="input-field"
                        size="small"
                        required
                    />
                </div>
                <div className="group-container">
                    <label className="default-label">Exposure:</label>
                    <TextField
                        label="seconds"
                        variant="outlined"
                        value={exposure}
                        onChange={(e) => handleExposureChange(e.target.value || 0)}
                        fullWidth
                        className="input-field"
                        size="small"
                        type="number"
                        onBlur={handleBlur}
                        inputProps={{
                            step: 0.1, 
                        }}
                    />
                </div>
                <div className="group-container" style={{justifyContent: 'space-between'}}>
                    <label className="default-label">ObsMode:</label>
                    <RadioGroup
                        row
                        value={obsmode}
                        onChange={(e) => setObsmode(e.target.value)}
                        className="radio-group"
                    >   
                        <FormControlLabel
                            value="Spec"
                            control={<Radio />}
                            label=<span className="bold-label">Spec</span>
                        />
                        <FormControlLabel
                            value="Deep"
                            control={<Radio />}
                            label=<span className="bold-label">Deep</span>
                        />
                    </RadioGroup>
                    <div className="collapse-toggle" onClick={toggleCollapse}>
                        {isCollapsed ? <ExpandMoreIcon /> : <ExpandLessIcon />}
                        <span className="collapse-text">
                            {isCollapsed ? 'Expand' : 'Collapse'}
                        </span>
                    </div>
                </div>

                {!isCollapsed && (
                    <>
                    {obsmode === 'Spec' && (
                        <SpecMode
                            specFileOptions={specFileOptions}
                            selectedSpecFile={selectedSpecFile}
                            setSelectedSpecFile={setSelectedSpecFile}
                            chartRef={chartRef}
                            filters={filters}
                        />
                    )}
                    {obsmode === 'Deep' && (
                        <DeepMode
                            selectedFilters={selectedFilters}
                            handleCheckboxChange={handleCheckboxChange}
                            selectedTelNumber={selectedTelNumber}
                            setSelectedTelNumber={setSelectedTelNumber}
                        />
                    )}
                    </>
                )}
                
                <label className="default-label">Comments:</label>
                <TextField
                        label="Any additional information"
                        variant="outlined"
                        value={comments}
                        onChange={(e) => setComments(e.target.value)}
                        fullWidth
                        className="input-field"
                        size="small"
                />

                <div className="group-container">
                    <FormControlLabel
                        control={
                            <Checkbox
                                checked={abortObservation}
                                onChange={(e) => setAbortObservation(e.target.checked)}
                                color="primary"
                            />
                        }
                        style={{fontWeight:'bold'}}
                        label={<span className="bold-label">Abort Current Observation?</span>}
                    />
                </div>

                <div className="collapse-toggle" style={{marginBottom: "0"}} onClick={toggleStaraltCollapse}>
                    {isStaraltCollapsed ? <ExpandMoreIcon /> : <ExpandLessIcon />}
                    <span className="collapse-text">
                        {isStaraltCollapsed ? 'Show Visibility' : 'Hide Visibility'}
                    </span>
                </div>
                {/* Display staralt plot */}
                {!isStaraltCollapsed && (
                    <>
                    {staraltData && (
                        <div style={{ width: '100%', height: '400px' }}>
                            <canvas ref={staraltChartRef} style={{ width: '100%', height: '100%' }}></canvas>
                        </div>
                    )}
                    </>
                )}

                <div className="collapse-toggle"  style={{marginTop: "0"}} onClick={toggleDetailCollapse}>
                    {isDetailCollapsed ? <ExpandMoreIcon /> : <ExpandLessIcon />}
                    <span className="collapse-text">
                        {isDetailCollapsed ? 'Show Detailed Settings' : 'Hide Detailed Settings'}
                    </span>
                </div>

                {!isDetailCollapsed && (
                    <>
                        <DetailedSettings
                            detailedSettings={detailedSettings}
                            setDetailedSettings={setDetailedSettings}
                            exposure={exposure}
                            setExposure={setExposure}
                        />
                    </>
                )}

                <Button
                    type="button"
                    variant="contained"
                    color="primary"
                    className="submit-button"
                    onClick={toggleDialog}
                >
                    Submit
                </Button>
            </form>
            <Dialog open={isDialogOpen} onClose={toggleDialog}>
                <DialogTitle>Confirm Submission</DialogTitle>
                <DialogContent>
                    <p><strong>Target:</strong> {target}</p>
                    <p><strong>R.A.:</strong> {ra}</p>
                    <p><strong>Dec.:</strong> {dec}</p>
                    <p><strong>Exposure:</strong> {exposure} seconds</p>
                    <p>
                        <strong>ObsMode:</strong> {obsmode}{" "}
                        {obsmode === "Spec" && `(${selectedSpecFile})`}
                        {obsmode === "Deep" && `(Filters: ${selectedFilters.join(", ")} | Telescopes: ${selectedTelNumber})`}
                    </p>
                    <p><strong>Comments:</strong> {comments}</p>
                    <p><strong>Abort Current Observation:</strong> {abortObservation ? 'Yes' : 'No'}</p>
                    <p><strong>Single Frame Exposure:</strong> {detailedSettings.singleFrameExposure} seconds</p>
                    <p><strong># of Images:</strong> {detailedSettings.imageCount}</p>
                    <p><strong>Priority:</strong> {detailedSettings.priority}</p>
                    <p><strong>Gain:</strong> {detailedSettings.gain}</p>
                    <p><strong>Binning:</strong> {detailedSettings.binning}</p>
                    <p><strong>Observation Start Time:</strong> {detailedSettings.obsStartTime}</p>
                </DialogContent>
                <DialogActions>
                    <Button onClick={toggleDialog} color="secondary">
                        Cancel
                    </Button>
                    <Button 
                        onClick={handleSubmit} 
                        variant="contained" 
                        color="primary"
                        disabled={isLoading}
                    >
                        {isLoading ? <CircularProgress size={24} color="inherit" /> : 'Confirm'}
                    </Button>
                </DialogActions>
            </Dialog>


            {/* Loading Message */}
            {isLoading && (
                <Snackbar open>
                    <Alert severity="info">
                        Sending email... Please wait.
                    </Alert>
                </Snackbar>
            )}


            {/* Success Message */}
            {successMessage && (
                <Snackbar open autoHideDuration={6000} onClose={() => setSuccessMessage('')}>
                    <Alert severity="success" onClose={() => setSuccessMessage('')}>
                        {successMessage}
                    </Alert>
                </Snackbar>
            )}

            {/* Error Message */}
            {error && (
                <Snackbar open autoHideDuration={6000} onClose={() => setError('')}>
                    <Alert severity="error" onClose={() => setError('')}>
                        {error}
                    </Alert>
                </Snackbar>
            )}

        </div>
    );
}

export default TargetForm;