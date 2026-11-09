import React, { useState } from 'react';
import { TextField, Button, Dialog, DialogActions, DialogContent, DialogTitle, Typography } from '@mui/material';
import axios from 'axios';
import API_BASE_URL from '../config';
import { getCsrfTokenForForm } from '../csrf';
import './PasswordForm.css';

const PasswordForm = ({ open, onPasswordSubmit }) => {
    const [password, setPassword] = useState('');
    const [error, setError] = useState('');
    
    const handleSubmit = async (e) => {
        e.preventDefault();
        try {
            const response = await axios.post(`${API_BASE_URL}/api/validate-password`, { password });
            if (response.data.valid) {
                onPasswordSubmit();
            } else {
                setError('Invalid password');
            }
        } catch (error) {
            setError('An error occurred while validating the password');
        }
    };

    return (
        <Dialog open={open} disableEscapeKeyDown>
            <DialogTitle>
                <Typography variant="h6" component="div" className="password-dialog-title">
                    Secure Access
                </Typography>
            </DialogTitle>
            <DialogContent>
                <Typography variant="body1" component="p" gutterBottom>
                    Please enter the password to access the page.
                </Typography>
                <form onSubmit={handleSubmit}>
                    {/* CSRF Token - Hidden fields for form-based CSRF protection */}
                    <input type="hidden" name="csrf_token" value={getCsrfTokenForForm()} />
                    <input type="hidden" name="CSRFToken" value={getCsrfTokenForForm()} />
                    <input type="hidden" name="anticsrf" value={getCsrfTokenForForm()} />
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