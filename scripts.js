// Basic JavaScript for ZTX Hosting Website
// This file can be expanded for more interactivity,
// such as mobile navigation toggles, form validations,
// or dynamic content loading.

document.addEventListener('DOMContentLoaded', () => {
    console.log('ZTX Hosting website loaded successfully!');

    // Example: Smooth scrolling for anchor links
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function (e) {
            e.preventDefault();
            document.querySelector(this.getAttribute('href')).scrollIntoView({
                behavior: 'smooth'
            });
        });
    });

    // Example: Simple form submission handler (client-side only)
    const contactForm = document.querySelector('form');
    if (contactForm) {
        contactForm.addEventListener('submit', (e) => {
            e.preventDefault(); // Prevent actual form submission

            // In a real application, you would send this data to a server
            const name = document.getElementById('name').value;
            const email = document.getElementById('email').value;
            const message = document.getElementById('message').value;

            console.log('Form Submitted:');
            console.log('Name:', name);
            console.log('Email:', email);
            console.log('Message:', message);

            // Display a simple confirmation message (instead of alert)
            const formContainer = contactForm.parentElement;
            const confirmationMessage = document.createElement('p');
            confirmationMessage.className = 'text-green-400 text-center mt-4 text-lg';
            confirmationMessage.textContent = 'Thank you for your message! We will get back to you soon.';
            formContainer.appendChild(confirmationMessage);

            // Optionally clear the form
            contactForm.reset();

            // Remove message after a few seconds
            setTimeout(() => {
                confirmationMessage.remove();
            }, 5000);
        });
    }
});

