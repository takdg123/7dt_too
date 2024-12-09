import React, { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import '../styles/TargetForm.css';
import {
    Autocomplete,
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
} from '@mui/material';

import {
    Chart as ChartJS,
    LinearScale,
    Title,
    Tooltip,
    ScatterController,
} from 'chart.js';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import ExpandLessIcon from '@mui/icons-material/ExpandLess';
import SpecMode from './SpecMode';
import DeepMode from './DeepMode';
import DetailedSettings from './DetailedSettings';

ChartJS.register(LinearScale, Title, Tooltip, ScatterController);

function TargetForm() {
    const [targets, setTargets] = useState([]);
    const [target, setTarget] = useState('');
    const [ra, setRa] = useState('');
    const [dec, setDec] = useState('');
    const [exposure, setExposure] = useState('5');
    const [mode, setMode] = useState('Spec'); 
    const [comments, setComments] = useState('');
    const [abortObservation, setAbortObservation] = useState(false); // Track checkbox state

    const [specFileOptions, setSpecFileOptions] = useState(['specall.specmode']);
    const [selectedSpecFile, setSelectedSpecFile] = useState('specall.specmode');
    const [isCustomTarget, setIsCustomTarget] = useState(true);
    const [wavelengths, setWavelengths] = useState([]);
    const [filters, setFilters] = useState([]);
    const [selectedFilters, setSelectedFilters] = useState(['g']); // For checkboxes
    const [selectedTelNumber, setSelectedTelNumber] = useState(10); // For dropdown

    const [isCollapsed, setIsCollapsed] = useState(true); // Collapse state for mode options
    const [isDetailCollapsed, setIsDetailCollapsed] = useState(true); // Collapse state for mode options
    const [isDialogOpen, setIsDialogOpen] = useState(false); // Dialog state

    const [detailedSettings, setDetailedSettings] = useState({
        singleFrameExposure: 60, // Default 60 seconds
        imageCount: 5, // Default exposure time / 60
        priority: 50, // Default 50
        gain: 2750, // Default 2750
        binning: 1, // Default 1
        obsStartTime: '', // Default empty
    });

    const chartRef = useRef(null);

    

    useEffect(() => {
        axios
            .get('http://127.0.0.1:5000/api/targets')
            .then((response) => setTargets(response.data))
            .catch((error) => console.error('Error fetching targets:', error));
    }, []);

    useEffect(() => {
        if (mode === 'Spec') {
            axios
                .get('http://127.0.0.1:5000/api/spec-options')
                .then((response) => setSpecFileOptions(response.data))
                .catch((error) => console.error('Error fetching spec file options:', error));
        }
    }, [mode]);

    useEffect(() => {
        if (selectedSpecFile) {
            axios
                .get(`http://127.0.0.1:5000/api/spec-file?file=${selectedSpecFile}`)
                .then((response) => {
                    setWavelengths(response.data.wavelengths);
                    setFilters(response.data.filters);
                })
                .catch((error) => console.error('Error fetching spec file data:', error));
        }
    }, [selectedSpecFile]);

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
                                ctx.fillStyle = 'green';
                                ctx.fillRect(
                                    xMin,
                                    chart.chartArea.top,
                                    xMax - xMin,
                                    chart.chartArea.bottom - chart.chartArea.top
                                );
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
    }, [wavelengths, mode, isCollapsed]);

    const handleSubmit = async () => {
        try {
            await axios.post('http://127.0.0.1:5000/api/send_email', {
                target,
                ra,
                dec,
                exposure,
                mode,
                comments,
                abortObservation,
                ...detailedSettings,
                ...(mode === 'Deep' && { selectedFilters, selectedTelNumber }),
                ...(mode === 'Spec' && { selectedSpecFile })
            });
            setIsDialogOpen(false); // Close dialog after submission
        } catch (error) {
            console.error('Error sending email:', error);
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
        const newSingleFrameExposure = newExposure / imageCount * 60;
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

    const toggleDialog = () => {
        setIsDialogOpen(!isDialogOpen);
    };


    return (
        <div className="container">
            <form onSubmit={handleSubmit} className="form">
                <div className="group-container">
                    <label className="default-label">Target:</label>
                    <Autocomplete
                        options={targets}
                        getOptionLabel={(option) => option.name || ''}
                        inputValue={target}
                        onInputChange={handleInputChange}
                        renderInput={(params) => (
                            <TextField {...params} label="Target" variant="outlined" fullWidth size="small" />
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
                    />
                </div>
                <div className="group-container">
                    <label className="default-label">Exposure:</label>
                    <TextField
                        label="minutes"
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
                    <label className="default-label">Mode:</label>
                    <RadioGroup
                        row
                        value={mode}
                        onChange={(e) => setMode(e.target.value)}
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
                    {mode === 'Spec' && (
                        <SpecMode
                            specFileOptions={specFileOptions}
                            selectedSpecFile={selectedSpecFile}
                            setSelectedSpecFile={setSelectedSpecFile}
                            chartRef={chartRef}
                            filters={filters}
                        />
                    )}
                    {mode === 'Deep' && (
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
                        label={<span className="bold-label">Abort Current Observation</span>}
                    />
                </div>

                <div className="collapse-toggle" onClick={toggleDetailCollapse}>
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
                        <strong>Mode:</strong> {mode}{" "}
                        {mode === "Spec" && `(${selectedSpecFile})`}
                        {mode === "Deep" && `(Filters: ${selectedFilters.join(", ")} | Telescopes: ${selectedTelNumber})`}
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
                    <Button onClick={handleSubmit} variant="contained" color="primary">
                        Confirm
                    </Button>
                </DialogActions>
            </Dialog>
        </div>
    );
}

export default TargetForm;