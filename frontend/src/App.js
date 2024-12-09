import React from 'react';
import StatusTable from './components/StatusTable';
import DailyScheduleTable from './components/DailyScheduleTable';
import TargetForm from './components/TargetForm';

import './App.css';

function App() {
    return (
        <div className="app-container">
            <header>
                <h1>7DT Target of Opportunity (ToO) Request</h1>
            </header>
            <section className="form-section">
                <TargetForm />
            </section>
            
            <header>
                <h1>Observatory Dashboard</h1>
            </header>
            <section className="dashboard-section">
                <StatusTable />
            </section>

            <section className="schedule-section">
                <DailyScheduleTable />
            </section>
        </div>
    );
}

export default App;