import React, { useState, useEffect } from 'react';
import axios from 'axios';
import API_BASE_URL from '../config';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import ExpandLessIcon from '@mui/icons-material/ExpandLess';
import EditIcon from '@mui/icons-material/Edit';
import RefreshIcon from '@mui/icons-material/Refresh';
import { Button, Dialog, DialogTitle, DialogContent, DialogActions, CircularProgress, Typography, TextField, ToggleButtonGroup, ToggleButton } from '@mui/material';
import '../styles/DailyScheduleTable.css';
import '../styles/TooTable.css';

function TooTable() {
    const [tooData, setTooData] = useState([]);
    const [loading, setLoading] = useState(true);
    const [expandedRows, setExpandedRows] = useState(new Set());
    const [openDialog, setOpenDialog] = useState({ open: false, type: null, rowData: null });
    const [dialogContent, setDialogContent] = useState({ content: null, loading: false, error: null, contentType: null });
    const [gcnTemplateContent, setGcnTemplateContent] = useState('');
    const [gcnTemplateModified, setGcnTemplateModified] = useState(false);
    const [gcnTemplateSaving, setGcnTemplateSaving] = useState(false);
    const [editCoordsDialog, setEditCoordsDialog] = useState({ open: false, rowData: null });
    const [editCoords, setEditCoords] = useState({ ra: '', dec: '' });
    const [coordsSaving, setCoordsSaving] = useState(false);
    const [lastUpdateTime, setLastUpdateTime] = useState(null);
    const [refreshing, setRefreshing] = useState(false);
    const [timezone, setTimezone] = useState('KST');

    const fetchTableData = (showRefreshing = false) => {
        if (showRefreshing) {
            setRefreshing(true);
        }
        axios.get(`${API_BASE_URL}/api/too_table`)
            .then((response) => {
                const data = Array.isArray(response.data) ? [...response.data] : [];
                const sortedData = data.sort((a, b) => {
                    const dateA = a.request_time || a.trigger_time ? new Date(a.request_time || a.trigger_time) : new Date(0);
                    const dateB = b.request_time || b.trigger_time ? new Date(b.request_time || b.trigger_time) : new Date(0);
                    return dateB - dateA; // Sort by requested date, descending
                });
                setTooData(sortedData);
                setLastUpdateTime(new Date());
                setLoading(false);
                setRefreshing(false);
            })
            .catch((error) => {
                console.error("Error fetching ToO table:", error);
                setTooData([]);
                setLoading(false);
                setRefreshing(false);
            });
    };

    useEffect(() => {
        // Fetch data immediately on mount
        fetchTableData();
        
        // Set up interval to refresh every 10 seconds
        const interval = setInterval(() => {
            fetchTableData();
        }, 10000);
        
        // Clean up interval on unmount
        return () => clearInterval(interval);
    }, []);


    const formatDate = (dateString) => {
        if (!dateString || dateString === '' || dateString === '""') return 'Not available';
        try {
            const date = new Date(dateString);
            if (isNaN(date.getTime())) return dateString;
            
            // Timezone mappings
            const timezoneMap = {
                'KST': 'Asia/Seoul',
                'UTC': 'UTC',
                'Chile': 'America/Santiago'
            };
            
            const timezoneLabel = {
                'KST': 'KST',
                'UTC': 'UTC',
                'Chile': 'CLT'
            };
            
            const tz = timezoneMap[timezone] || 'Asia/Seoul';
            const formatted = date.toLocaleString('en-US', {
                year: 'numeric',
                month: 'short',
                day: 'numeric',
                hour: '2-digit',
                minute: '2-digit',
                second: '2-digit',
                hour12: false,
                timeZone: tz
            });
            
            return `${formatted} (${timezoneLabel[timezone]})`;
        } catch {
            return dateString;
        }
    };

    const formatColumnValue = (value) => {
        if (value === null || value === undefined || value === '' || value === '""') return 'N/A';
        return String(value);
    };

    const formatCoordinate = (value) => {
        const formatted = formatColumnValue(value);
        return formatted !== 'N/A' ? `${formatted}°` : 'N/A';
    };

    const isProcessed = (v2) => {
        const checkValue = (value) => {
            if (!value) return false;
            const v = String(value).toLowerCase().trim();
            return v === 'true' || v === 'available' || v === 'processed';
        };
        return checkValue(v2);
    };

    const getV2ProgressColor = (v2_progress) => {
        if (!v2_progress) return '#F44336'; // Red for null/undefined
        const progress = parseFloat(v2_progress);
        if (isNaN(progress)) return '#F44336'; // Red if not a number
        if (progress === 100) return '#4CAF50'; // Green for 100%
        if (progress > 0 && progress < 100) return '#FFC107'; // Yellow for 0-100%
        return '#F44336'; // Red for 0 or negative
    };

    const formatV2Status = (v2_progress) => {
        if (!v2_progress) return 'Not processed';
        const progress = parseFloat(v2_progress);
        if (isNaN(progress)) return 'Not processed';
        if (progress === 100) return 'Processed';
        if (progress > 0 && progress < 100) return 'Processing';
        return 'Not processed';
    };

    const getStatus = (v1, v2, v2_progress) => {
        // Check v2_progress first
        if (v2_progress !== null && v2_progress !== undefined && v2_progress !== '') {
            const progress = parseFloat(v2_progress);
            if (!isNaN(progress)) {
                if (progress === 100) return 'Processed';
                if (progress > 0 && progress < 100) return 'Processing';
            }
        }
        
        // If v2_progress indicates not processed or is not available, check v2
        if (isProcessed(v2)) {
            return 'Processed';
        }
        
        // If v2 is not processed, check v1
        if (isProcessed(v1)) {
            return 'Processed (gppy)';
        }
        
        // Both are not processed
        return 'Not processed';
    };

    const getStatusColor = (v1, v2, v2_progress) => {
        // Check v2_progress first
        if (v2_progress !== null && v2_progress !== undefined && v2_progress !== '') {
            const progress = parseFloat(v2_progress);
            if (!isNaN(progress)) {
                if (progress === 100) return '#4CAF50'; // Green for processed
                if (progress > 0 && progress < 100) return '#FFC107'; // Yellow for processing
            }
        }
        
        // If v2_progress indicates not processed or is not available, check v2
        if (isProcessed(v2)) {
            return '#4CAF50'; // Green for processed
        }
        
        // If v2 is not processed, check v1
        if (isProcessed(v1)) {
            return '#FFA500'; // Orange for processed (gppy)
        }
        
        // Both are not processed
        return '#F44336'; // Red for not processed
    };

    const getVStatusColor = (value) => {
        if (!value) return '#F44336'; // Red for null/undefined
        const v = String(value).toLowerCase().trim();
        if (v === 'true' || v === 'available' || v === 'processed') return '#4CAF50'; // Green
        return '#F44336'; // Red for "not processed" or other values
    };

    const getVStatusColorClass = (value) => {
        const color = getVStatusColor(value);
        return color === '#4CAF50' ? 'too-color-green' : 'too-color-red';
    };

    const getV2ProgressColorClass = (v2_progress) => {
        const color = getV2ProgressColor(v2_progress);
        if (color === '#4CAF50') return 'too-color-green';
        if (color === '#FFC107') return 'too-color-yellow';
        return 'too-color-red';
    };

    const getStatusColorClass = (v1, v2, v2_progress) => {
        const color = getStatusColor(v1, v2, v2_progress);
        if (color === '#4CAF50') return 'too-color-green';
        if (color === '#FFC107') return 'too-color-yellow';
        if (color === '#FFA500') return 'too-color-orange';
        return 'too-color-red';
    };

    const formatVStatus = (value) => {
        if (!value) return 'Not processed';
        const v = String(value).toLowerCase().trim();
        if (v === 'true' || v === 'available' || v === 'processed') return 'Processed';
        return 'Not processed';
    };

    const toggleRow = (index) => {
        const newExpanded = new Set(expandedRows);
        if (newExpanded.has(index)) {
            newExpanded.delete(index);
        } else {
            newExpanded.add(index);
        }
        setExpandedRows(newExpanded);
    };

    const getWikiLink = (objname) => {
        objname = objname?.replace(" ", "") || '';
        return <a href={`https://proton.snu.ac.kr/en/ToO/${objname}`} target="_blank" rel="noopener noreferrer">Wiki</a>;
    };

    const isFileAvailable = (filePath) => {
        if (!filePath || filePath === 'null' || filePath === '' || filePath === '""') {
            return false;
        }
        return true;
    };

    const isGcnTemplateAvailable = (rowData) => {
        // Check if gcn_template file path is available
        return isFileAvailable(rowData.gcn_template);
    };

    const handleOpenDialog = async (type, rowData) => {
        setOpenDialog({ open: true, type, rowData });
        
        if (type === 'image_list') {
            // Handle image list display - show image_list and catalog_list from rowData
            setDialogContent({ 
                imageList: rowData.image_list || null,
                catalogList: rowData.catalog_list || null,
                loading: false, 
                error: null, 
                contentType: 'image_list' 
            });
        } else if (type === 'gcn_template') {
            // Fetch GCN template
            setDialogContent({ content: null, loading: true, error: null, contentType: null });
            setGcnTemplateContent('');
            setGcnTemplateModified(false);

            // Get file path from gcn_template field
            const filePath = rowData.gcn_template;

            // Check if file path is available
            if (!filePath || filePath === 'null' || filePath === '' || filePath === '""') {
                setDialogContent({ 
                    content: null, 
                    loading: false, 
                    error: 'GCN template file path not available', 
                    contentType: null 
                });
                return;
            }

            // Clean up the file path (remove quotes if present)
            const cleanFilePath = filePath.replace(/^"|"$/g, '');

            // Fetch template from backend
            try {
                const response = await axios.get(`${API_BASE_URL}/api/gcn-template`, {
                    params: { file_path: cleanFilePath }
                });

                if (response.data.error) {
                    setDialogContent({ 
                        content: null, 
                        loading: false, 
                        error: response.data.error, 
                        contentType: null 
                    });
                } else {
                    const templateContent = response.data.content || '';
                    setGcnTemplateContent(templateContent);
                    setDialogContent({ 
                        content: templateContent, 
                        loading: false, 
                        error: null, 
                        contentType: 'gcn_template',
                        source: response.data.source || 'default',
                        path: response.data.path || cleanFilePath
                    });
                }
            } catch (error) {
                console.error('Error fetching GCN template:', error);
                setDialogContent({ 
                    content: null, 
                    loading: false, 
                    error: error.response?.data?.error || error.message || 'Failed to fetch GCN template', 
                    contentType: null 
                });
            }
        } else if (type === 'images_sed') {
            // Fetch Images and SED
            setDialogContent({ content: null, loading: true, error: null, contentType: null });

            const alertKey = rowData.alert_key;
            if (!alertKey) {
                setDialogContent({ 
                    content: null, 
                    loading: false, 
                    error: 'Alert key not available', 
                    contentType: null 
                });
                return;
            }

            try {
                // Fetch both image and text in parallel
                const [imageResult, textResult] = await Promise.allSettled([
                    axios.get(`${API_BASE_URL}/api/output`, {
                        params: { 
                            alert_key: alertKey,
                            type: 'image'
                        },
                        responseType: 'blob'
                    }),
                    axios.get(`${API_BASE_URL}/api/output`, {
                        params: { 
                            alert_key: alertKey,
                            type: 'text'
                        },
                        responseType: 'text'
                    })
                ]);

                let imageUrl = null;
                let textContent = null;
                const errors = [];

                // Process image result
                if (imageResult.status === 'fulfilled') {
                    imageUrl = URL.createObjectURL(imageResult.value.data);
                } else {
                    let errorMsg = imageResult.reason?.response?.data?.error || imageResult.reason?.message || 'Failed to fetch image';
                    const blob = imageResult.reason?.response?.data;
                    if (blob instanceof Blob) {
                        try { errorMsg = JSON.parse(await blob.text()).error || errorMsg; } catch (e) { /* not JSON */ }
                    }
                    errors.push(`Image: ${errorMsg}`);
                }

                // Process text result
                if (textResult.status === 'fulfilled') {
                    textContent = textResult.value.data;
                } else {
                    const errorMsg = textResult.reason?.response?.data?.error || textResult.reason?.message || 'Failed to fetch text';
                    errors.push(`Text: ${errorMsg}`);
                }

                // If both failed, show error. Otherwise show partial results with warnings
                if (!imageUrl && !textContent) {
                    setDialogContent({ 
                        content: null, 
                        loading: false, 
                        error: errors.join('; '), 
                        contentType: null 
                    });
                } else {
                    setDialogContent({ 
                        imageUrl: imageUrl,
                        textContent: textContent,
                        loading: false, 
                        error: errors.length > 0 ? errors.join('; ') : null, 
                        contentType: 'images_sed'
                    });
                }
            } catch (error) {
                console.error('Error fetching Images and SED:', error);
                setDialogContent({ 
                    content: null, 
                    loading: false, 
                    error: error.response?.data?.error || error.message || 'Failed to fetch Images and SED', 
                    contentType: null 
                });
            }
        } else {
            // For other dialogs, reset content
            setDialogContent({ content: null, loading: false, error: null, contentType: null });
        }
    };

    const handleCloseDialog = () => {
        // Clean up image URL if it exists
        if (dialogContent.imageUrl) {
            URL.revokeObjectURL(dialogContent.imageUrl);
        }
        setOpenDialog({ open: false, type: null, rowData: null });
        setDialogContent({ content: null, loading: false, error: null, contentType: null });
        setGcnTemplateContent('');
        setGcnTemplateModified(false);
        setGcnTemplateSaving(false);
    };

    const handleSaveGcnTemplate = async () => {
        const rowData = openDialog.rowData;
        if (!rowData) return;

        // Get file path from dialogContent or rowData.gcn_template
        let filePath = dialogContent.path || rowData.gcn_template;
        
        if (!filePath || filePath === 'null' || filePath === '' || filePath === '""') {
            setDialogContent(prev => ({ ...prev, error: 'GCN template file path not available for saving' }));
            return;
        }

        // Clean up the file path (remove quotes if present)
        filePath = filePath.replace(/^"|"$/g, '');

        setGcnTemplateSaving(true);
        try {
            const response = await axios.post(`${API_BASE_URL}/api/gcn-template`, 
                { content: gcnTemplateContent },
                { params: { file_path: filePath } }
            );

            if (response.data.error) {
                setDialogContent(prev => ({ ...prev, error: response.data.error }));
            } else {
                setGcnTemplateModified(false);
                setDialogContent(prev => ({ 
                    ...prev, 
                    error: null,
                    source: 'custom',
                    path: filePath
                }));
                // Show success message
                alert('Template saved successfully!');
            }
        } catch (error) {
            console.error('Error saving GCN template:', error);
            setDialogContent(prev => ({ 
                ...prev, 
                error: error.response?.data?.error || error.message || 'Failed to save template' 
            }));
        } finally {
            setGcnTemplateSaving(false);
        }
    };

    const handleOpenEditCoords = (rowData) => {
        // Initialize with current values (prefer ra/dec, fallback to ra_deg/dec_deg)
        // Handle null/undefined explicitly to allow 0 as a valid value
        const currentRa = rowData.ra != null ? rowData.ra : (rowData.ra_deg != null ? rowData.ra_deg : '');
        const currentDec = rowData.dec != null ? rowData.dec : (rowData.dec_deg != null ? rowData.dec_deg : '');
        setEditCoords({ 
            ra: currentRa !== '' ? String(currentRa) : '', 
            dec: currentDec !== '' ? String(currentDec) : '' 
        });
        setEditCoordsDialog({ open: true, rowData });
    };

    const handleCloseEditCoords = () => {
        setEditCoordsDialog({ open: false, rowData: null });
        setEditCoords({ ra: '', dec: '' });
    };

    const parseRA = (value) => {
        if (!value || value === '') return null;
        
        const trimmed = String(value).trim();
        
        // Check if it's in HH:MM:SS format
        if (trimmed.includes(':')) {
            const parts = trimmed.split(':');
            if (parts.length >= 2) {
                const hours = parseFloat(parts[0]);
                const minutes = parseFloat(parts[1]) || 0;
                const seconds = parts.length >= 3 ? parseFloat(parts[2]) || 0 : 0;
                
                if (isNaN(hours) || isNaN(minutes) || isNaN(seconds)) {
                    return null;
                }
                
                // Convert hours:minutes:seconds to degrees (1 hour = 15 degrees)
                return hours * 15 + minutes * 15 / 60 + seconds * 15 / 3600;
            }
        }
        
        // Try parsing as a number (degrees)
        const num = parseFloat(trimmed);
        return isNaN(num) ? null : num;
    };

    const parseDec = (value) => {
        if (!value || value === '') return null;
        
        const trimmed = String(value).trim();
        
        // Check if it's in DD:MM:SS format
        if (trimmed.includes(':')) {
            const parts = trimmed.split(':');
            if (parts.length >= 2) {
                const degrees = parseFloat(parts[0]);
                const minutes = parseFloat(parts[1]) || 0;
                const seconds = parts.length >= 3 ? parseFloat(parts[2]) || 0 : 0;
                
                if (isNaN(degrees) || isNaN(minutes) || isNaN(seconds)) {
                    return null;
                }
                
                // Convert degrees:minutes:seconds to decimal degrees
                const sign = degrees < 0 ? -1 : 1;
                return sign * (Math.abs(degrees) + minutes / 60 + seconds / 3600);
            }
        }
        
        // Try parsing as a number (degrees)
        const num = parseFloat(trimmed);
        return isNaN(num) ? null : num;
    };

    const handleSaveCoords = async () => {
        const rowData = editCoordsDialog.rowData;
        if (!rowData) return;

        const ra = parseRA(editCoords.ra);
        const dec = parseDec(editCoords.dec);

        if (ra === null || dec === null) {
            alert('Please enter valid values for RA and Dec (numeric or HH:MM:SS/DD:MM:SS format)');
            return;
        }

        setCoordsSaving(true);
        try {
            const response = await axios.put(`${API_BASE_URL}/api/too_table/coordinates`, {
                alert_key: rowData.alert_key,
                ra: ra,
                dec: dec
            });

            if (response.data.error) {
                alert(`Error: ${response.data.error}`);
            } else {
                alert('Coordinates updated successfully!');
                handleCloseEditCoords();
                // Refresh table data
                fetchTableData();
            }
        } catch (error) {
            console.error('Error saving coordinates:', error);
            alert(error.response?.data?.error || error.message || 'Failed to save coordinates');
        } finally {
            setCoordsSaving(false);
        }
    };

    if (loading) {
        return <p>Loading data...</p>;
    }

    return (
        <div className="container">
            <div className="too-header">
                <h3>Requested ToO List</h3>
                <div className="too-header-actions">
                    {lastUpdateTime && (
                        <Typography variant="body2" className="too-timezone-label">
                            Last updated: {formatDate(lastUpdateTime.toISOString())}
                        </Typography>
                    )}
                    <Button
                        variant="outlined"
                        size="small"
                        startIcon={refreshing ? <CircularProgress size={16} /> : <RefreshIcon />}
                        onClick={() => fetchTableData(true)}
                        disabled={refreshing}
                    >
                        {refreshing ? 'Refreshing...' : 'Refresh'}
                    </Button>
                </div>
            </div>
            <div className="too-timezone-section">
                <div className="too-timezone-controls">
                    <Typography variant="body2" className="too-timezone-label">
                        Timezone:
                    </Typography>
                    <ToggleButtonGroup
                        value={timezone}
                        exclusive
                        onChange={(e, newTimezone) => {
                            if (newTimezone !== null) {
                                setTimezone(newTimezone);
                            }
                        }}
                        size="small"
                        aria-label="timezone selection"
                        className="too-toggle-button-group"
                    >
                        <ToggleButton 
                            value="KST" 
                            aria-label="KST"
                            className="too-toggle-button"
                        >
                            KST
                        </ToggleButton>
                        <ToggleButton 
                            value="UTC" 
                            aria-label="UTC"
                            className="too-toggle-button"
                        >
                            UTC
                        </ToggleButton>
                        <ToggleButton 
                            value="Chile" 
                            aria-label="Chile"
                            className="too-toggle-button"
                        >
                            Chile
                        </ToggleButton>
                    </ToggleButtonGroup>
                </div>
            </div>
            <div className="table-container">
                    <table className="compact-table">
                        <thead>
                            <tr>
                                <th className="too-table-expand-icon"></th>
                                <th>ID</th>
                                <th>Object Name</th>
                                <th>Requester</th>
                                <th>Requested Date</th>
                                <th>Observing Date</th>
                                <th>Status</th>
                            </tr>
                        </thead>
                        <tbody>
                        {tooData.length > 0 ? (
                            tooData.map((row, index) => {
                                const isExpanded = expandedRows.has(index);
                                return (
                                    <React.Fragment key={`${row.objname}-${index}`}>
                                        <tr 
                                            className="too-table-row-clickable"
                                            onClick={() => toggleRow(index)}
                                        >
                                            <td className="too-table-expand-icon">
                                                {isExpanded ? <ExpandLessIcon /> : <ExpandMoreIcon />}
                                            </td>
                                            <td>{row.id || 'N/A'}</td>
                                            <td>{row.objname || 'N/A'}</td>
                                            <td>{formatColumnValue(row.requester)}</td>
                                            <td>{formatDate(row.request_time || row.trigger_time)}</td>
                                            <td>{formatDate(row.observation_time)}</td>
                                            <td>
                                                <span 
                                                    className={`too-status-text ${getStatusColorClass(row.v1, row.v2, row.v2_progress)}`}
                                                >
                                                    {getStatus(row.v1, row.v2, row.v2_progress)}
                                                </span>
                                            </td>
                                        </tr>
                                        {isExpanded && (
                                            <tr>
                                                <td colSpan="7" className="too-expanded-row">
                                                    <div className="too-expanded-content">
                                                        {/* Header Section */}
                                                        <div className="too-expanded-header">
                                                            <h3 className="too-expanded-title">
                                                                {row.objname || 'Unknown Object'} (Tile: {row.tile || 'N/A'})
                                                            </h3>
                                                            <div className="too-expanded-subtitle">
                                                                Alert Key: {row.alert_key ? (
                                                                    <code className="too-code">
                                                                        {formatColumnValue(row.alert_key)}
                                                                    </code>
                                                                ) : 'N/A'}
                                                            </div>
                                                        </div>

                                                        {/* Basic Information Section */}
                                                        <div className="too-section">
                                                            <h4 className="too-section-title">
                                                                Basic Information
                                                            </h4>
                                                            <table className="too-info-table">
                                                                <tbody>
                                                                    <tr>
                                                                        <td className="too-info-table-label">
                                                                            Requester
                                                                        </td>
                                                                        <td>
                                                                            {formatColumnValue(row.requester)}
                                                                        </td>
                                                                    </tr>
                                                                    <tr>
                                                                        <td className="too-info-table-label">
                                                                            Coordinates
                                                                        </td>
                                                                        <td>
                                                                            <div className="too-coords-container">
                                                                                <div className="too-coords-info">
                                                                                    <div>
                                                                                        <strong>RA:</strong> {formatCoordinate(row.ra)} ({formatCoordinate(row.ra_deg)})
                                                                                    </div>
                                                                                    <div>
                                                                                        <strong>Dec:</strong> {formatCoordinate(row.dec)} ({formatCoordinate(row.dec_deg)})
                                                                                    </div>
                                                                                </div>
                                                                                <Button
                                                                                    variant="outlined"
                                                                                    size="small"
                                                                                    startIcon={<EditIcon />}
                                                                                    onClick={(e) => {
                                                                                        e.stopPropagation();
                                                                                        handleOpenEditCoords(row);
                                                                                    }}
                                                                                    className="too-edit-button"
                                                                                >
                                                                                    Edit
                                                                                </Button>
                                                                            </div>
                                                                        </td>
                                                                    </tr>
                                                                    <tr>
                                                                        <td className="too-info-table-label">
                                                                            Exposure Settings
                                                                        </td>
                                                                        <td>
                                                                            <span className="too-info-span">
                                                                                <strong>Exposure:</strong> {formatColumnValue(row.exptime)} s
                                                                            </span>
                                                                            <span>
                                                                                <strong>N Images:</strong> {formatColumnValue(row.n_image)}
                                                                            </span>
                                                                        </td>
                                                                    </tr>
                                                                    <tr>
                                                                        <td className="too-info-table-label">
                                                                            Camera Settings
                                                                        </td>
                                                                        <td>
                                                                            <span className="too-info-span">
                                                                                <strong>Gain:</strong> {formatColumnValue(row.gain)}
                                                                            </span>
                                                                            <span>
                                                                                <strong>Binning:</strong> {formatColumnValue(row.binning)}
                                                                            </span>
                                                                        </td>
                                                                    </tr>
                                                                    {(row.obsmode || row.priority || row.obs_starttime || row.radius || row.specmode) && (
                                                                        <tr>
                                                                            <td className="too-info-table-label">
                                                                                Observation Settings
                                                                            </td>
                                                                            <td>
                                                                                {row.obsmode && (
                                                                                    <span className="too-info-span">
                                                                                        <strong>Mode:</strong> {formatColumnValue(row.obsmode)}
                                                                                    </span>
                                                                                )}
                                                                                {row.priority && (
                                                                                    <span className="too-info-span">
                                                                                        <strong>Priority:</strong> {formatColumnValue(row.priority)}
                                                                                    </span>
                                                                                )}
                                                                                {row.specmode && (
                                                                                    <div className="too-info-div">
                                                                                        <strong>Spec Mode:</strong> {formatColumnValue(row.specmode)}
                                                                                    </div>
                                                                                )}
                                                                                {row.obs_starttime && formatColumnValue(row.obs_starttime) !== 'N/A' && (
                                                                                    <div className="too-info-div">
                                                                                        <strong>Obs Start Time:</strong> {formatDate(row.obs_starttime)}
                                                                                    </div>
                                                                                )}
                                                                                {row.radius && formatColumnValue(row.radius) !== 'N/A' && (
                                                                                    <div className="too-info-div">
                                                                                        <strong>Radius:</strong> {formatColumnValue(row.radius)}°
                                                                                    </div>
                                                                                )}
                                                                            </td>
                                                                        </tr>
                                                                    )}
                                                                    {row.comments && (
                                                                        <tr>
                                                                            <td className="too-info-table-label too-info-table-label-top">
                                                                                Comments
                                                                            </td>
                                                                            <td>
                                                                                {row.comments}
                                                                            </td>
                                                                        </tr>
                                                                    )}
                                                                </tbody>
                                                            </table>
                                                        </div>

                                                        {/* Time History Section */}
                                                        <div className="too-section">
                                                            <h4 className="too-section-title">
                                                                Time History
                                                            </h4>
                                                            <table className="too-info-table">
                                                                <tbody>
                                                                    <tr>
                                                                        <td className="too-info-table-label too-info-table-label-wide">
                                                                            Request Time
                                                                        </td>
                                                                        <td>
                                                                            {formatDate(row.request_time || row.trigger_time)}
                                                                        </td>
                                                                    </tr>
                                                                    <tr>
                                                                        <td className="too-info-table-label">
                                                                            Observation Time
                                                                        </td>
                                                                        <td>
                                                                            {formatDate(row.observation_time)}
                                                                        </td>
                                                                    </tr>
                                                                    <tr>
                                                                        <td className="too-info-table-label">
                                                                            Transfer Time
                                                                        </td>
                                                                        <td>
                                                                            {formatDate(row.transfer_time)}
                                                                        </td>
                                                                    </tr>
                                                                    <tr>
                                                                        <td className="too-info-table-label">
                                                                            Processed Time
                                                                        </td>
                                                                        <td>
                                                                            {formatDate(row.processed_time)}
                                                                        </td>
                                                                    </tr>
                                                                </tbody>
                                                            </table>
                                                        </div>

                                                        {/* Status Section */}
                                                        <div className="too-section">
                                                            <h4 className="too-section-title">
                                                                Data Reduction Status
                                                            </h4>
                                                            <div className="too-status-container">
                                                                <div 
                                                                    className={`too-status-card ${getVStatusColorClass(row.v1)}-border`}
                                                                >
                                                                    <div className="too-status-label">
                                                                        gppy
                                                                    </div>
                                                                    <div 
                                                                        className={`too-status-value ${getVStatusColorClass(row.v1)}-text`}
                                                                    >
                                                                        {formatVStatus(row.v1)}
                                                                    </div>
                                                                    <div className="too-status-note">
                                                                        Status: not tracked
                                                                    </div>
                                                                </div>
                                                                <div 
                                                                    className={`too-status-card too-status-card-large ${getV2ProgressColorClass(row.v2_progress)}-border`}
                                                                >
                                                                    <div className="too-status-label too-status-label-large">
                                                                        py7dt
                                                                    </div>
                                                                    <div 
                                                                        className={`too-status-value too-status-value-large ${getV2ProgressColorClass(row.v2_progress)}-text`}
                                                                    >
                                                                        {formatV2Status(row.v2_progress)}
                                                                    </div>
                                                                    {row.v2_status && (
                                                                        <div className="too-status-note">
                                                                            Status: {formatColumnValue(row.v2_status)}
                                                                        </div>
                                                                    )}
                                                                </div>
                                                                {(row.is_ToO || row.is_rapidToO) && (
                                                                    <div className="too-status-card too-status-card-large too-status-card-purple">
                                                                        <div className="too-status-label too-status-label-large">
                                                                            ToO Type
                                                                        </div>
                                                                        <div className="too-status-value too-status-value-large too-status-value-purple">
                                                                            {row.is_rapidToO === true || row.is_rapidToO === 'True' ? 'Rapid ToO' : 
                                                                             row.is_ToO === true || row.is_ToO === 'True' ? 'ToO' : 'Standard'}
                                                                        </div>
                                                                    </div>
                                                                )}
                                                            </div>
                                                        </div>


                                                        {/* Output Section */}
                                                        <div>
                                                            <h4 className="too-section-title">
                                                                Results
                                                            </h4>
                                                            <div className="too-expanded-subtitle">
                                                                Output Directory: {row.base_path ? (
                                                                    <code className="too-code">
                                                                        {formatColumnValue(row.base_path)}
                                                                    </code>
                                                                ) : 'N/A'}
                                                            </div>
                                                            <div className="too-results-section">
                                                                <div className="too-results-buttons">
                                                                    <Button
                                                                        variant="contained"
                                                                        color="primary"
                                                                        size="large"
                                                                        fullWidth
                                                                        className="too-results-button-large"
                                                                        onClick={() => handleOpenDialog('images_sed', row)}
                                                                    >
                                                                        Images and SED
                                                                    </Button>
                                                                    <div className="too-results-button-group">
                                                                        <Button
                                                                            variant="outlined"
                                                                            size="small"
                                                                            disabled={!isFileAvailable(row.file_list)}
                                                                            className="too-results-button-small"
                                                                            onClick={() => handleOpenDialog('image_list', row)}
                                                                        >
                                                                            Image list
                                                                        </Button>
                                                                        <Button
                                                                            variant="outlined"
                                                                            size="small"
                                                                            disabled={!isGcnTemplateAvailable(row)}
                                                                            className="too-results-button-small"
                                                                            onClick={() => handleOpenDialog('gcn_template', row)}
                                                                        >
                                                                            GCN template
                                                                        </Button>
                                                                    </div>
                                                                </div>
                                                            </div>
                                                        </div>
                </div>
                                                </td>
                                            </tr>
                                        )}
                                    </React.Fragment>
                                );
                            })
                        ) : (
                            <tr><td colSpan="7" className="too-no-data">No data available</td></tr>
                        )}
                    </tbody>
                </table>
            </div>

            {/* Dialog for Images and SED */}
            <Dialog 
                open={openDialog.open && openDialog.type === 'images_sed'} 
                onClose={handleCloseDialog}
                maxWidth="lg"
                fullWidth
            >
                <DialogTitle>
                    Images and SED - {openDialog.rowData?.objname || 'N/A'}
                </DialogTitle>
                <DialogContent>
                    {dialogContent.loading && (
                        <div className="too-dialog-loading">
                            <CircularProgress />
                            <Typography variant="body2" className="too-dialog-loading-text">
                                Loading Images and SED...
                            </Typography>
                        </div>
                    )}
                    {dialogContent.error && dialogContent.contentType !== 'images_sed' && (
                        <div className="too-dialog-error">
                            <Typography variant="body1" color="error">
                                {dialogContent.error}
                            </Typography>
                        </div>
                    )}
                    {!dialogContent.loading && dialogContent.contentType === 'images_sed' && (
                        <div className="too-dialog-content">
                            {/* Warning for partial errors */}
                            {dialogContent.error && (
                                <div className="too-dialog-warning">
                                    <Typography variant="body2">
                                        <strong>Warning:</strong> {dialogContent.error}
                                    </Typography>
                                </div>
                            )}
                            {/* Image Section */}
                            {dialogContent.imageUrl && (
                                <div className="too-dialog-image-section">
                                    <Typography variant="h6" className="too-dialog-section-title">
                                        Spectral Energy Distribution and Cutout images
                                    </Typography>
                                    <div className="too-dialog-image-container">
                                        <img 
                                            src={dialogContent.imageUrl} 
                                            alt="Combined SED Cutouts" 
                                            className="too-dialog-image"
                                        />
                                    </div>
                                </div>
                            )}
                            {/* Text Section */}
                            {dialogContent.textContent && (
                                <div>
                                    <Typography variant="h6" className="too-dialog-section-title">
                                        7DT Observation Summary
                                    </Typography>
                                    <div className="too-dialog-text-container">
                                        {dialogContent.textContent}
                                    </div>
                                </div>
                            )}
                        </div>
                    )}
                </DialogContent>
                <DialogActions>
                    <Button onClick={handleCloseDialog}>Close</Button>
                </DialogActions>
            </Dialog>

            {/* Dialog for Image List */}
            <Dialog 
                open={openDialog.open && openDialog.type === 'image_list'} 
                onClose={handleCloseDialog}
                maxWidth="md"
                fullWidth
            >
                <DialogTitle>
                    Image List - {openDialog.rowData?.objname || 'N/A'}
                </DialogTitle>
                <DialogContent>
                    {dialogContent.loading && (
                        <div className="too-dialog-loading">
                            <CircularProgress />
                            <Typography variant="body2" className="too-dialog-loading-text">
                                Loading image list...
                            </Typography>
                        </div>
                    )}
                    {dialogContent.error && (
                        <div className="too-dialog-error">
                            <Typography variant="body1" color="error">
                                {dialogContent.error}
                            </Typography>
                        </div>
                    )}
                    {!dialogContent.loading && !dialogContent.error && dialogContent.contentType === 'image_list' && (
                        <div className="too-dialog-list-container">
                            {/* Images Section */}
                            <div>
                                <Typography variant="h6" className="too-dialog-section-title">
                                    Images:
                                </Typography>
                                {dialogContent.imageList ? (
                                    <pre className="too-dialog-pre">
                                        {typeof dialogContent.imageList === 'string' 
                                            ? dialogContent.imageList 
                                            : JSON.stringify(dialogContent.imageList, null, 2)}
                                    </pre>
                                ) : (
                                    <Typography variant="body2" className="too-dialog-empty-text">
                                        No image list available
                                    </Typography>
                                )}
                            </div>
                            
                            {/* Catalogs Section */}
                            <div>
                                <Typography variant="h6" className="too-dialog-section-title">
                                    Catalogs:
                                </Typography>
                                {dialogContent.catalogList ? (
                                    <pre className="too-dialog-pre">
                                        {typeof dialogContent.catalogList === 'string' 
                                            ? dialogContent.catalogList 
                                            : JSON.stringify(dialogContent.catalogList, null, 2)}
                                    </pre>
                                ) : (
                                    <Typography variant="body2" className="too-dialog-empty-text">
                                        No catalog list available
                                    </Typography>
                                )}
                            </div>
                        </div>
                    )}
                </DialogContent>
                <DialogActions>
                    <Button onClick={handleCloseDialog}>Close</Button>
                </DialogActions>
            </Dialog>

            {/* Dialog for GCN template */}
            <Dialog 
                open={openDialog.open && openDialog.type === 'gcn_template'} 
                onClose={handleCloseDialog}
                maxWidth="md"
                fullWidth
            >
                <DialogTitle>
                    GCN Template - {openDialog.rowData?.objname || 'N/A'}
                    {dialogContent.source && (
                        <Typography variant="caption" className="too-dialog-source-caption">
                            Source: {dialogContent.source === 'custom' ? 'Custom template' : 'Default template'}
                        </Typography>
                    )}
                </DialogTitle>
                <DialogContent>
                    {dialogContent.loading && (
                        <div className="too-dialog-loading">
                            <CircularProgress />
                            <Typography variant="body2" className="too-dialog-loading-text">
                                Loading GCN template...
                            </Typography>
                        </div>
                    )}
                    {dialogContent.error && (
                        <div className="too-dialog-error">
                            <Typography variant="body1" color="error">
                                {dialogContent.error}
                            </Typography>
                        </div>
                    )}
                    {!dialogContent.loading && !dialogContent.error && (
                        <div className="too-dialog-edit-container">
                            <TextField
                                fullWidth
                                multiline
                                rows={15}
                                value={gcnTemplateContent}
                                onChange={(e) => {
                                    setGcnTemplateContent(e.target.value);
                                    setGcnTemplateModified(true);
                                }}
                                variant="outlined"
                                className="too-dialog-textfield"
                                InputProps={{
                                    className: "too-dialog-textfield-input"
                                }}
                            />
                        </div>
                    )}
                </DialogContent>
                <DialogActions>
                    <Button onClick={handleCloseDialog}>Close</Button>
                    {!dialogContent.loading && !dialogContent.error && (
                        <Button 
                            onClick={handleSaveGcnTemplate}
                            variant="contained"
                            color="primary"
                            disabled={!gcnTemplateModified || gcnTemplateSaving}
                        >
                            {gcnTemplateSaving ? (
                                <>
                                    <CircularProgress size={16} className="too-dialog-save-button" />
                                    Saving...
                                </>
                            ) : (
                                'Save'
                            )}
                        </Button>
                    )}
                </DialogActions>
            </Dialog>

            {/* Dialog for Edit Coordinates */}
            <Dialog 
                open={editCoordsDialog.open} 
                onClose={handleCloseEditCoords}
                maxWidth="sm"
                fullWidth
            >
                <DialogTitle>
                    Edit Coordinates - {editCoordsDialog.rowData?.objname || 'N/A'}
                </DialogTitle>
                <DialogContent>
                    <div className="too-dialog-edit-container">
                        <TextField
                            label="RA (degrees or HH:MM:SS)"
                            type="text"
                            value={editCoords.ra}
                            onChange={(e) => setEditCoords({ ...editCoords, ra: e.target.value })}
                            variant="outlined"
                            fullWidth
                            placeholder="e.g., 232.12 or 15:28:48"
                        />
                        <TextField
                            label="Dec (degrees or DD:MM:SS)"
                            type="text"
                            value={editCoords.dec}
                            onChange={(e) => setEditCoords({ ...editCoords, dec: e.target.value })}
                            variant="outlined"
                            fullWidth
                            placeholder="e.g., -22.11 or -22:06:36"
                        />
                    </div>
                </DialogContent>
                <DialogActions>
                    <Button onClick={handleCloseEditCoords}>Cancel</Button>
                    <Button 
                        onClick={handleSaveCoords}
                        variant="contained"
                        color="primary"
                        disabled={coordsSaving}
                    >
                        {coordsSaving ? (
                            <>
                                <CircularProgress size={16} className="too-dialog-save-button" />
                                Saving...
                            </>
                        ) : (
                            'Save'
                        )}
                    </Button>
                </DialogActions>
            </Dialog>
        </div>
    );
}

export default TooTable;