// Бандл дизайн-системы берёт React из window.React — отдаём ему тот же экземпляр, что у приложения.
import React from 'react'

window.React = React
