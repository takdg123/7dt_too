import React, { useState, useEffect } from 'react';
import axios from 'axios';
import CircleIcon from '@mui/icons-material/Circle';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import ExpandLessIcon from '@mui/icons-material/ExpandLess';
import '../styles/StatusTable.css';

function StatusTable() {
    const [tableData, setTableData] = useState([]);
    const [filtInfo, setFiltInfo] = useState([]);
    const [latestReport, setLatestReport] = useState({});
    const [loading, setLoading] = useState(true);
    const [isDetailCollapsed, setIsDetailCollapsed] = useState(true); // State for collapse/expand

    useEffect(() => {
        // Fetch data from both endpoints
        const fetchStatusData = axios.get('http://127.0.0.1:5000/api/status');
        const fetchFiltInfoData = axios.get('http://127.0.0.1:5000/api/filtinfo');

        Promise.all([fetchStatusData, fetchFiltInfoData])
            .then(([statusResponse, filtInfoResponse]) => {
                setTableData(statusResponse.data.table);
                setLatestReport(statusResponse.data.latest_report);
                setFiltInfo(filtInfoResponse.data);
                setLoading(false);
            })
            .catch((error) => {
                console.error("Error fetching data:", error);
                setLoading(false);
            });
    }, []);

    const getStatusIcon = (status) => {
        const iconStyle = { width: "15px", height: "15px", margin: "0", padding: "0" };

        if (status === "operational") return <CircleIcon style={{ ...iconStyle, color: "green" }} />;
        if (status === "maintanance") return <CircleIcon style={{ ...iconStyle, color: "yellow" }} />;
        if (status === "offline") return <CircleIcon style={{ ...iconStyle, color: "red" }} />;
        return <CircleIcon style={{ ...iconStyle, color: "gray" }} />;
    };

    // Determine summary status for each telescope
    const getSummaryStatus = (row) => {
        const statuses = ['Mount', 'Focuser', 'Filterwheel', 'Camera'].map((component) => row[component]);
        if (statuses.includes('offline')) return 'offline'; // Red if any component is offline
        if (statuses.includes('maintanance')) return 'maintanance'; // Yellow if any component is maintenance
        return 'operational'; // Green if all components are operational
    };

    // Merge tableData and filtInfo based on Telescope
    const combinedData = tableData.map((statusRow) => {
        const filtInfoRow = filtInfo.find((filt) => filt.Telescope === statusRow.Telescope);
        return {
            ...statusRow,
            Filters: filtInfoRow ? filtInfoRow.Filters.join(', ') : 'No filters available',
        };
    });

    const toggleDetailCollapse = () => {
        setIsDetailCollapsed(!isDetailCollapsed);
    };

    if (loading) {
        return <p>Loading data...</p>;
    }

    // Split the telescopes into two rows
    const row1 = tableData.slice(0, 10);
    const row2 = tableData.slice(10, 20);

    return (
        <div className="container">
            {/* Compact Summary Table */}
            <h2>Current Status</h2>
            <div className="summary-grid">
                {[row1, row2].map((row, rowIndex) => (
                    <div key={rowIndex} className="summary-row">
                        {row.map((telescope, index) => (
                            <div key={index} className="summary-item">
                                <div className="summary-telescope">{telescope.Telescope}</div>
                                <div className="summary-icon">
                                    {getStatusIcon(getSummaryStatus(telescope))}
                                </div>
                            </div>
                        ))}
                    </div>
                ))}
            </div>

            {/* Expand/Collapse Toggle */}
            <div className="collapse-toggle" onClick={toggleDetailCollapse}>
                {isDetailCollapsed ? <ExpandMoreIcon /> : <ExpandLessIcon />}
                <span className="collapse-text">
                    {isDetailCollapsed ? 'Show Detailed Status' : 'Hide Detailed Status'}
                </span>
            </div>

            {/* Combined Table */}
            {!isDetailCollapsed && (
                <div>
                    <h3>Telescope Status and Filter Information</h3>
                    <table border="1" cellPadding="5" cellSpacing="0" style={{ width: '100%' }}>
                        <thead>
                            <tr>
                                <th>Telescope</th>
                                <th>Mount</th>
                                <th>Focuser</th>
                                <th>Filterwheel</th>
                                <th>Camera</th>
                                <th>Filters</th>
                            </tr>
                        </thead>
                        <tbody>
                            {combinedData.map((row, index) => (
                                <tr key={index}>
                                    <td>{row.Telescope}</td>
                                    <td>{getStatusIcon(row.Mount)}</td>
                                    <td>{getStatusIcon(row.Focuser)}</td>
                                    <td>{getStatusIcon(row.Filterwheel)}</td>
                                    <td>{getStatusIcon(row.Camera)}</td>
                                    <td>{row.Filters}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                    <p className="footer">
                        Reported by {latestReport.reported_by} on {latestReport.timestamp}
                    </p>
                </div>
            )}
        </div>
    );
}

export default StatusTable;