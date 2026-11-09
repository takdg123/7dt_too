import React from 'react';
import { Select, MenuItem } from '@mui/material';
import '../styles/ColOptions.css';

function SpecMode({ specFileOptions, selectedSpecFile, setSelectedSpecFile, chartRef, filters }) {
    
    return (
        <div className="mode-options">
            {/* Spec File Dropdown */}
            <div className="group-container">
                <label className="smaller-label">Spec File:</label>
                <Select
                    value={selectedSpecFile}
                    onChange={(e) => setSelectedSpecFile(e.target.value)}
                    size="small"
                >
                    {specFileOptions.map((file) => (
                        <MenuItem key={file} value={file}>
                            {file}
                        </MenuItem>
                    ))}
                </Select>
            </div>

            {/* Wavelength Chart */}
            
            <label className="smaller-label">Medium band coverage (Å):</label>
            
            <div className="group-container chart-container">
                <canvas ref={chartRef} className="wavelength-chart" />
            </div>

            {/* Filters Table */}
            <div className="group-container">
                <label className="smaller-label">Broad band coverage:</label>
                <div className="table-container">
                    <table className="filters-table">
                        <tbody>
                            <tr>
                                {['u', 'g', 'r', 'i', 'z'].map((filter) => (
                                    <td
                                        key={filter}
                                        className={`filter-cell ${
                                            filters.includes(filter) ? 'filter-active' : 'filter-inactive'
                                        }`}
                                    >
                                        {filter}
                                    </td>
                                ))}
                            </tr>
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    );
}

export default SpecMode;