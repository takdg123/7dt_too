import React, { useEffect } from 'react';
import { Button,TextField, RadioGroup, FormControlLabel, Radio } from '@mui/material';
import '../styles/ColOptions.css';

function DetailedSettings({ detailedSettings, setDetailedSettings, exposure, setExposure }) {
    const defaultValues = {
        singleFrameExposure: 60,
        imageCount: 5,
        priority: 50,
        gain: 2750,
        binning: 1,
        obsStartTime: '',
    };

    const {
        singleFrameExposure,
        imageCount,
        priority,
        gain,
        binning,
        obsStartTime,
    } = detailedSettings;

    const handleInputChange = (field, value) => {
        setDetailedSettings((prev) => ({
            ...prev,
            [field]: value,
        }));
    };

    const handleReset = () => {
        setDetailedSettings(defaultValues);
        setExposure(defaultValues.singleFrameExposure * defaultValues.imageCount);
    };

    // Automatically calculate `exposure` based on `singleFrameExposure` and `imageCount`
    useEffect(() => {
        const calculatedExposure = singleFrameExposure * imageCount;
        if (exposure !== calculatedExposure) {
            setExposure(calculatedExposure);
        }
    }, [singleFrameExposure, imageCount, setExposure, exposure]);

    return (
        <div className="mode-options">
            <div className="group-container">
                <label className="detail-label">Single Frame Exposure Time:</label>
                <TextField
                    value={singleFrameExposure}
                    onChange={(e) => handleInputChange('singleFrameExposure', e.target.value)}
                    type="number"
                    variant="outlined"
                    size="small"
                    label="seconds"
                    inputProps={{
                        step: 0.1, 
                    }}
                />
            </div>

            <div className="group-container">
                <label className="detail-label"># of Images:</label>
                <TextField
                    value={imageCount}
                    onChange={(e) => handleInputChange('imageCount', parseInt(e.target.value||1))}
                    type="number"
                    variant="outlined"
                    size="small"
                    label="counts"
                />
            </div>

            <div className="group-container">
                <label className="detail-label">Priority:</label>
                <TextField
                    value={priority}
                    onChange={(e) => handleInputChange('priority', parseInt(e.target.value||0))}
                    type="number"
                    variant="outlined"
                    size="small"
                />
            </div>

            <div className="group-container">
                <label className="detail-label">Gain:</label>
                <TextField
                    value={gain}
                    onChange={(e) => handleInputChange('gain', parseInt(e.target.value||0))}
                    type="number"
                    variant="outlined"
                    size="small"
                />
            </div>

            <div className="group-container">
                <label className="detail-label">Binning:</label>
                <RadioGroup
                    row
                    value={binning}
                    onChange={(e) => handleInputChange('binning', parseInt(e.target.value))}
                >
                    <FormControlLabel value={1} control={<Radio />} label="1" />
                    <FormControlLabel value={2} control={<Radio />} label="2" />
                </RadioGroup>
            </div>

            <div className="group-container">
                <label className="detail-label">Observation Start Time:</label>
                <TextField
                    value={obsStartTime}
                    onChange={(e) => handleInputChange('obsStartTime', e.target.value)}
                    type="datetime-local"
                    variant="outlined"
                    size="small"
                    inputProps={{
                        step: 1, 
                    }}
                />
            </div>
            <div className='reset-button-container'>
                <Button
                    className="reset-button"
                    onClick={handleReset}
                    variant="outlined"
                    color="secondary"
                    size="small"
                >
                    Reset to Defaults
                </Button>
            </div>
        </div>
    );
}

export default DetailedSettings;