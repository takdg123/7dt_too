import React, { useState } from 'react';
import { TextField, Button, Dialog, DialogActions, DialogContent, DialogTitle, Typography } from '@mui/material';

const PasswordForm = ({ open, onPasswordSubmit }) => {
    const [password, setPassword] = useState('');
    const [error, setError] = useState('');
    
    const handlePasswordSubmit = (event) => {
        event.preventDefault(); // Prevent the default form submission behavior
        const correctPassword = process.env.REACT_APP_SDT_PASSWORD;
        if (password === correctPassword) {
            onPasswordSubmit();
        } else {
            setError('Incorrect password. Please try again.');
        }
    };

    return (
        <Dialog open={open} disableEscapeKeyDown>
            <DialogTitle>
                <Typography variant="h6" component="div" style={{color:"red", fontWeight:"bold"}}>
                    Secure Access
                </Typography>
            </DialogTitle>
            <DialogContent>
                <Typography variant="body1" component="p" gutterBottom>
                    Please enter the password to access the page.
                </Typography>
                <form onSubmit={handlePasswordSubmit}>
                    <TextField
                        autoFocus
                        margin="dense"
                        label="Password"
                        type="password"
                        fullWidth
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        error={!!error}
                        helperText={error}
                    />
                    <DialogActions>
                        <Button type="submit" color="primary" variant="contained">
                            Submit
                        </Button>
                    </DialogActions>
                </form>
            </DialogContent>
        </Dialog>
    );
};

export default PasswordForm;