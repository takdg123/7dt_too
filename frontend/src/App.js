import React, { useState } from 'react';
import { Tabs, Tab, Box } from '@mui/material';
import StatusTable from './components/StatusTable';
import DailyScheduleTable from './components/DailyScheduleTable';
import TargetForm from './components/TargetForm';
import TooTable from './components/TooTable';
import PasswordForm from './components/PasswordForm';

import './App.css';

function TabPanel({ children, value, index }) {
    return (
        <div role="tabpanel" hidden={value !== index}>
            {value === index && <Box className="tab-panel">{children}</Box>}
        </div>
    );
}

function App() {
    const [isPasswordFormOpen, setIsPasswordFormOpen] = useState(true);
    const [currentTab, setCurrentTab] = useState(0);

    const handlePasswordSubmit = () => {
        setIsPasswordFormOpen(false);
    };

    const handleTabChange = (event, newValue) => {
        setCurrentTab(newValue);
    };

    return (
        <div className="app-container">
            {!isPasswordFormOpen && (
                <>
                    <header>
                        <h1>7DT Target of Opportunity (ToO) Request</h1>
                    </header>

                    <Box className="tabs-container">
                        <Tabs value={currentTab} onChange={handleTabChange} centered>
                            <Tab label="Request" />
                            <Tab label="History" />
                            <Tab label="Daily Schedule" />
                            <Tab label="Telescope Status" />
                        </Tabs>
                    </Box>

                    <TabPanel value={currentTab} index={0}>
                        <TargetForm />
                    </TabPanel>

                    <TabPanel value={currentTab} index={1}>
                        <TooTable />
                    </TabPanel>

                    <TabPanel value={currentTab} index={2}>
                        <DailyScheduleTable />
                    </TabPanel>

                    <TabPanel value={currentTab} index={3}>
                        <StatusTable />
                    </TabPanel>

                    <footer className="footer">
                        <div className="footer-content">
                            <p>If you have any questions, please contact: 
                                <a href="mailto:myungshin.im@gmail.com?cc=hhchoi1022@gmail.com"> Prof. Myungshin Im</a>
                            </p>
                        </div>
                    </footer>
                </>
            )}
            <PasswordForm open={isPasswordFormOpen} onPasswordSubmit={handlePasswordSubmit} />
        </div>
    );
}

export default App;