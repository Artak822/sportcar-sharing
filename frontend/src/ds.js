// Компоненты дизайн-системы Pitlane (../design-system). Порядок импортов важен: сначала window.React.
import './react-global.js'
import '../../design-system/tokens.css'
import '../../design-system/components/bundle.css'
import '../../design-system/components/bundle.js'

export const { Button, Badge, Input, CarCard, SpecList, BookingSummary, AgentMessage, AgentAction } = window.Pitlane
